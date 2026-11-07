import { RefObject, useEffect } from 'react';

// Reveal the label/help with its control, not just the inner native input.
export function reveal(element: HTMLElement) {
  const region = element.closest<HTMLElement>('.dd-scroll');
  if (!region) { element.scrollIntoView({ block: 'nearest', inline: 'nearest' }); return; }
  const form = element.closest<HTMLElement>('.dd-form');
  let field = element;
  if (form) while (field.parentElement && field.parentElement !== form) field = field.parentElement;
  const box = region.getBoundingClientRect(), rect = field.getBoundingClientRect();
  const first = form?.firstElementChild === field;
  if (first) region.scrollTop = 0;
  else if (rect.height <= region.clientHeight - 16) {
    if (rect.top < box.top + 8) region.scrollTop -= box.top + 8 - rect.top;
    else if (rect.bottom > box.bottom - 8) region.scrollTop += rect.bottom - box.bottom + 8;
  } else {
    const control = element.getBoundingClientRect();
    if (control.top < box.top + 8) region.scrollTop -= box.top + 8 - control.top;
    else if (control.bottom > box.bottom - 8) region.scrollTop += control.bottom - box.bottom + 8;
  }
}

export function focus(element?: HTMLElement | null) {
  const win = element?.ownerDocument.defaultView;
  if (!win || !element) return;
  element.dispatchEvent(new win.CustomEvent('vgp_requestfocus', { bubbles: true, cancelable: true, detail: { button: 1, source: 0 } }));
  element.focus({ preventScroll: true });
  reveal(element);
  // Steam may scroll its inner TextField after handling requestfocus. Restore
  // the whole field after that layout, without continuously fighting touch.
  win.requestAnimationFrame(() => win.requestAnimationFrame(() => {
    if (element.isConnected && (element === element.ownerDocument.activeElement || element.contains(element.ownerDocument.activeElement))) reveal(element);
  }));
}

export function usePageFocus(root: RefObject<HTMLElement>, page: string) {
  useEffect(() => {
    const win = root.current?.ownerDocument.defaultView;
    const timer = win?.setTimeout(() => {
      // Do not steal focus if the user already started navigating this page.
      if (root.current?.contains(root.current.ownerDocument.activeElement)) return;
      focus(root.current?.querySelector<HTMLElement>('[data-autofocus]:not(:disabled)') ||
        root.current?.querySelector<HTMLElement>('button:not(:disabled)'));
    }, 70);
    return () => { if (timer) win?.clearTimeout(timer); };
  }, [root, page]);
}

// Steam's keyboard animates in a different document from the plugin script.
// Measure that document so the input and form actions stay above the keyboard.
export function useKeyboardSpace(root: RefObject<HTMLElement>) {
  useEffect(() => {
    let win: Window | null | undefined, frame = 0, retry = 0;
    let modal: HTMLElement | null | undefined;
    let keyboardLayout = '', lastInput: HTMLElement | undefined;
    function measure() {
      const doc = root.current?.ownerDocument;
      win = doc?.defaultView;
      if (!win) { retry = window.setTimeout(measure, 30); return; }
      const active = doc?.activeElement as HTMLElement | null;
      if (active && root.current?.contains(active) && active.matches('input,textarea')) lastInput = active;
      modal = root.current?.closest<HTMLElement>('.dd-modal');
      const rect = doc?.getElementById('virtual keyboard')?.getBoundingClientRect();
      const visible = !!rect && rect.width > 0 && rect.height > 0 && rect.top < win.innerHeight && rect.bottom > 0;
      modal?.classList.toggle('dd-keyboard', visible);
      if (visible && rect) {
        const above = Math.max(0, rect.top), below = Math.max(0, win.innerHeight - rect.bottom);
        modal?.style.setProperty('--dd-keyboard-top', `${above >= below ? 4 : rect.bottom + 4}px`);
        modal?.style.setProperty('--dd-keyboard-height', `${Math.max(100, Math.max(above, below) - 8)}px`);
      }
      const nextLayout = visible && rect ? `${rect.top}:${rect.bottom}` : '';
      if (nextLayout !== keyboardLayout && visible && lastInput?.isConnected) {
        // Resizing a fixed modal does not automatically reveal its focused
        // field. Reposition once per keyboard size change, not on every frame.
        lastInput.scrollIntoView({ block: 'center', inline: 'nearest' });
      }
      keyboardLayout = nextLayout;
      frame = win.requestAnimationFrame(measure);
    }
    measure();
    return () => {
      window.clearTimeout(retry); win?.cancelAnimationFrame(frame);
      modal?.classList.remove('dd-keyboard');
      modal?.style.removeProperty('--dd-keyboard-top'); modal?.style.removeProperty('--dd-keyboard-height');
    };
  }, [root]);
}
