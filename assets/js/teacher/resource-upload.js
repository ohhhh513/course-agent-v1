'use strict';

window.TeacherResourceUpload = (() => {
  const TYPES = Object.freeze({
    doc: { label: '教材文献', accept: '.pdf,.doc,.docx,.txt' },
    ppt: { label: '课件', accept: '.pdf,.ppt,.pptx' },
    video: { label: '教学视频', accept: '.mp4,.mov,.webm,.mkv' },
  });

  function extension(file) {
    const name = String((file && file.name) || '').toLowerCase();
    const dot = name.lastIndexOf('.');
    return dot >= 0 ? name.slice(dot) : '';
  }

  function validate(type, file) {
    const config = TYPES[type];
    if (!config) return '请先选择资源类型。';
    if (!file) return '请先选择文件。';
    if (!config.accept.split(',').includes(extension(file))) {
      return `所选文件与「${config.label}」不匹配，请检查文件格式。`;
    }
    return '';
  }

  function attach(typeInput, fileInput) {
    const syncType = () => {
      const config = TYPES[typeInput.value];
      fileInput.disabled = !config;
      fileInput.accept = config ? config.accept : '';
      if (fileInput.files[0] && validate(typeInput.value, fileInput.files[0])) {
        fileInput.value = '';
        if (window.Toast) Toast.warn('资源类型已更改', '请重新选择匹配的文件');
      }
    };

    typeInput.addEventListener('change', syncType);
    fileInput.addEventListener('change', () => {
      const message = validate(typeInput.value, fileInput.files[0]);
      if (!message) return;
      fileInput.value = '';
      if (window.Toast) Toast.error('文件类型不匹配', message);
    });
    syncType();
  }

  return { attach, validate, labels: Object.freeze(Object.fromEntries(
    Object.entries(TYPES).map(([key, value]) => [key, value.label])
  )) };
})();
