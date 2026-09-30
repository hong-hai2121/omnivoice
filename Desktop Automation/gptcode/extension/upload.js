// Called on the file input through CDP before dispatching the upload events.
export function observeUpload() {
  const input = this;
  let captured = null;
  const capture = event => {
    if (event.composedPath().includes(input) && input.files?.length) captured = input.files[0];
  };
  const targets = [...new Set([input.ownerDocument.defaultView, input.ownerDocument, input.getRootNode(), input])];
  for (const target of targets) for (const type of ["input", "change"]) target.addEventListener(type, capture, true);
  return {
    async read() {
      // React-style upload handlers may reset or remove the input synchronously.
      const file = captured || input.files?.[0];
      if (!file) return null;
      const result = { name: file.name, size: file.size, fromEvent: !!captured, readable: false };
      try { result.readable = (await file.slice(0, 1).arrayBuffer()).byteLength === 1; }
      catch (error) { result.readError = error.name; }
      return result;
    },
    dispose() {
      for (const target of targets) for (const type of ["input", "change"]) target.removeEventListener(type, capture, true);
      captured = null;
    },
  };
}
