// Browser-only adapter. Production builds always use @decky/ui from Steam.
import React, { forwardRef, useEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
export const GamepadButton = { SECONDARY: 3, OPTIONS: 4, BUMPER_LEFT: 5, BUMPER_RIGHT: 6, DIR_UP: 9, DIR_DOWN: 10, DIR_LEFT: 11, DIR_RIGHT: 12 };
export type GamepadEvent = CustomEvent<{ button: number }>;
export const Focusable = forwardRef<HTMLDivElement, any>(function Focusable(props, ref) {
  const { children, onButtonDown, onCancelButton, onGamepadDirection, onSecondaryActionDescription, onOptionsActionDescription,
    onCancelActionDescription, ...rest } = props;
  const own = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const node = own.current;
    const listener = (event: Event) => {
      const button = event as GamepadEvent;
      if (button.detail.button >= 9 && button.detail.button <= 12) onGamepadDirection?.(button);
      else if (button.detail.button === 2) onCancelButton?.(button); else onButtonDown?.(button);
    };
    node?.addEventListener('dd-gamepad', listener);
    return () => node?.removeEventListener('dd-gamepad', listener);
  }, [onButtonDown, onCancelButton, onGamepadDirection]);
  return <div {...rest} ref={node => { own.current = node; if (typeof ref === 'function') ref(node); else if (ref) ref.current = node; }}>{children}</div>;
});
export const DialogButton = ({ children, onGamepadFocus, ...rest }: any) => <button type="button" onFocus={onGamepadFocus} {...rest}>{children}</button>;
export const ModalRoot = ({ children, className }: any) => <div className="preview-modal-frame"><div className={className}>{children}</div></div>;
export const DropdownItem = ({ label, selectedOption, rgOptions, onChange }: any) => <label className="preview-field">{label}<select value={selectedOption} onChange={e => onChange(rgOptions.find((o: any) => String(o.data) === e.target.value))}>
  {rgOptions.map((o: any) => <option key={o.data} value={o.data}>{o.label}</option>)}</select></label>;
export const TextField = ({ label, focusOnMount, bIsPassword, ...rest }: any) => <label className="preview-field">{label}<input autoFocus={focusOnMount} type={bIsPassword ? 'password' : 'text'} {...rest} /></label>;
export function showModal(content: React.ReactElement, _parent: unknown, options: any) {
  const container = document.createElement('div');
  document.body.append(container);
  const root = createRoot(container);
  let closed = false;
  // Steam returns the raw modal handle. Only the injected closeModal calls
  // fnOnClose; calling handle.Close() directly skips that callback.
  const Close = () => { if (!closed) { closed = true; root.unmount(); container.remove(); } };
  root.render(React.cloneElement(content, { closeModal: () => { Close(); options?.fnOnClose?.(); } }));
  return { Close };
}
