(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const form = $('convert-form');
  const textarea = $('url-input');
  const fileInput = $('file-input');
  const dropZone = $('drop-zone');
  const selectedFiles = $('selected-files');
  const resultsList = $('results-list');
  const resultEmpty = $('result-empty');
  const resultDescription = $('results-description');
  const downloadAll = $('download-all');
  const processButton = $('convert-button');
  let files = [];
  let zipBlob = null;
  let objectUrls = [];

  // Detect pasted links even when concatenated without spaces.
  // Split at every http(s) prefix; sanitize punctuation typically trailing in prose.
  const lines = () => [...new Set(
    (textarea.value.match(/https?:\/\/.*?(?=https?:\/\/|$)/gis) || [])
      .map((part) => part.trim().split(/\s/)[0].replace(/[),;\]}]+$/, ''))
      .filter(Boolean)
  )];
  const humanSize = (bytes) => bytes > 1024 * 1024 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
  const showError = (message) => {
    const e = $('error-banner');
    e.textContent = message;
    e.hidden = !message;
  };
  const updateCount = () => {
    const count = lines().length + files.length;
    $('count').textContent = String(count);
    $('count').style.color = count > 100 ? '#d74d59' : '';
  };
  const updateFiles = () => {
    selectedFiles.replaceChildren();
    files.forEach((file, index) => {
      const row = document.createElement('div'); row.className = 'selected-file';
      const name = document.createElement('span'); name.textContent = file.name;
      const size = document.createElement('small'); size.textContent = humanSize(file.size);
      const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '×';
      remove.setAttribute('aria-label', `Remove ${file.name}`);
      remove.onclick = () => { files.splice(index, 1); updateFiles(); updateCount(); };
      row.append(name, size, remove); selectedFiles.append(row);
    });
  };
  const addFiles = (incoming) => {
    for (const f of incoming) {
      if (files.some((existing) => existing.name === f.name && existing.size === f.size && existing.lastModified === f.lastModified)) continue;
      files.push(f);
    }
    updateFiles(); updateCount();
    showError('');
    fileInput.value = '';
  };
  textarea.addEventListener('input', updateCount);
  $('clear-urls').addEventListener('click', () => { textarea.value = ''; updateCount(); showError(''); });
  $('paste-btn').addEventListener('click', async () => {
    try {
      const clip = await navigator.clipboard.readText();
      textarea.value = [textarea.value.trim(), clip.trim()].filter(Boolean).join('\n');
      updateCount();
    } catch { showError('Clipboard access is unavailable. Use Ctrl+V (or long-press → Paste) in the link field.'); }
  });
  dropZone.addEventListener('click', () => fileInput.click());
  dropZone.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); fileInput.click(); } });
  fileInput.addEventListener('change', () => addFiles([...fileInput.files]));
  ['dragenter', 'dragover'].forEach((type) => dropZone.addEventListener(type, (ev) => {
    ev.preventDefault(); dropZone.classList.add('dragging');
  }));
  ['dragleave', 'drop'].forEach((type) => dropZone.addEventListener(type, (ev) => {
    ev.preventDefault(); dropZone.classList.remove('dragging');
  }));
  dropZone.addEventListener('drop', (ev) => addFiles([...ev.dataTransfer.files]));
  document.querySelectorAll('.option-card input, .quality-card input').forEach((input) => {
    input.addEventListener('change', () => {
      document.querySelectorAll(`input[name="${input.name}"]`).forEach((other) => {
        other.closest('label').classList.toggle('selected', other.checked);
      });
    });
  });

  function readStoredZip(buffer) {
    // zipfile.ZIP_STORED local entries have known sizes.  No dependency needed.
    const view = new DataView(buffer);
    const bytes = new Uint8Array(buffer);
    const decoder = new TextDecoder();
    const entries = new Map();
    let offset = 0;
    while (offset + 30 <= bytes.length && view.getUint32(offset, true) === 0x04034b50) {
      const flags = view.getUint16(offset + 6, true);
      const compression = view.getUint16(offset + 8, true);
      const size = view.getUint32(offset + 18, true);
      const nameLen = view.getUint16(offset + 26, true);
      const extraLen = view.getUint16(offset + 28, true);
      if (flags & 8 || compression !== 0) throw new Error('Unsupported ZIP encoding.');
      const begin = offset + 30;
      const dataStart = begin + nameLen + extraLen;
      if (dataStart + size > bytes.length) throw new Error('Incomplete download.');
      const name = decoder.decode(bytes.subarray(begin, begin + nameLen));
      entries.set(name, bytes.slice(dataStart, dataStart + size));
      offset = dataStart + size;
    }
    return entries;
  }
  function hrefFor(content, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    objectUrls.push(url);
    return url;
  }
  function revokeOld() {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    objectUrls = [];
  }
  function renderResults(manifest, entries) {
    resultsList.replaceChildren();
    resultEmpty.hidden = true;
    const ok = manifest.items.filter((item) => item.files.length).length;
    const bad = manifest.items.length - ok;
    resultDescription.textContent = `${ok} item${ok === 1 ? '' : 's'} prepared${bad ? ` · ${bad} couldn't be processed` : ' successfully'}. Download your files below.`;
    for (const item of manifest.items) {
      const row = document.createElement('div'); row.className = 'result-entry';
      const head = document.createElement('div'); head.className = 'result-entry-head';
      const indicator = document.createElement('span'); indicator.className = `result-status${item.error ? ' failed' : ''}`;
      indicator.textContent = item.error ? '!' : '✓';
      const details = document.createElement('div');
      const name = document.createElement('p'); name.className = 'result-entry-title'; name.textContent = item.title;
      details.appendChild(name);
      if (item.note) {
        const note = document.createElement('small');
        note.textContent = item.note;
        details.appendChild(note);
      }
      if (item.error) {
        const err = document.createElement('div'); err.className = 'result-entry-error'; err.textContent = item.error;
        details.appendChild(err);
      }
      head.append(indicator, details); row.appendChild(head);
      if (item.files.length) {
        const links = document.createElement('div'); links.className = 'result-file-list';
        for (const info of item.files) {
          const bytes = entries.get(info.name);
          if (!bytes) continue;
          const button = document.createElement('button'); button.type = 'button';
          button.textContent = `↓ ${info.format.toUpperCase()} · ${humanSize(info.size)}`;
          button.onclick = () => {
            const contentType = info.format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
            const a = document.createElement('a'); a.href = hrefFor(bytes, contentType); a.download = info.name;
            document.body.append(a); a.click(); a.remove();
          };
          links.appendChild(button);
        }
        row.appendChild(links);
      }
      resultsList.appendChild(row);
    }
    downloadAll.hidden = false;
    $('result-card').scrollIntoView({behavior:'smooth',block:'nearest'});
  }
  downloadAll.addEventListener('click', () => {
    if (!zipBlob) return;
    const a = document.createElement('a'); a.href = hrefFor(zipBlob, 'application/zip'); a.download = 'slideforge-batch.zip';
    document.body.append(a); a.click(); a.remove();
  });
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault(); showError('');
    const urls = lines();
    if (!urls.length && !files.length) { showError('Add at least one link or upload a file to begin.'); textarea.focus(); return; }
    if (urls.length + files.length > 100) { showError('A batch can contain up to 100 items. Remove some and try again.'); return; }
    if (files.some((f) => f.size > 25 * 1024 * 1024)) { showError('Each uploaded file must be 25 MB or less.'); return; }
    const fd = new FormData();
    fd.append('urls', JSON.stringify(urls));
    fd.append('fmt', form.querySelector('input[name="fmt"]:checked').value);
    fd.append('quality', form.querySelector('input[name="quality"]:checked').value);
    files.forEach((file) => fd.append('files', file, file.name));
    processButton.disabled = true;
    processButton.querySelector('.button-default').hidden = true;
    processButton.querySelector('.button-loading').hidden = false;
    try {
      const response = await fetch('/api/download', {method: 'POST', body: fd});
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        const details = result.items?.map((item) => `${item.title}: ${item.error}`).join(' | ');
        throw new Error(details || (typeof result.detail === 'string' ? result.detail : 'Unable to process this batch.'));
      }
      if (!(response.headers.get('content-type') || '').includes('application/zip')) throw new Error('Unexpected server response.');
      const archive = await response.arrayBuffer();
      const entries = readStoredZip(archive);
      const metadata = entries.get('manifest.json');
      if (!metadata) throw new Error('The server did not return a manifest.');
      const manifest = JSON.parse(new TextDecoder().decode(metadata));
      revokeOld();
      zipBlob = new Blob([archive], {type:'application/zip'});
      renderResults(manifest, entries);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Unable to connect to the conversion server.');
    } finally {
      processButton.disabled = false;
      processButton.querySelector('.button-default').hidden = false;
      processButton.querySelector('.button-loading').hidden = true;
    }
  });
  updateCount();
})();
