import { Focusable, FocusableProps, GamepadButton, GamepadEvent } from '@decky/ui';
import { forwardRef } from 'react';
import { focus, reveal } from './layout';

const controls = 'button,input,select,textarea,[role="button"],[role="combobox"],[tabindex="0"]';
const vertical = (button: number) => button === GamepadButton.DIR_UP || button === GamepadButton.DIR_DOWN;

function visibleRect(element: HTMLElement, root: HTMLElement) {
  const rect = element.getBoundingClientRect();
  let top = rect.top, bottom = rect.bottom, left = rect.left, right = rect.right;
  for (let parent = element.parentElement; parent; parent = parent.parentElement) {
    const style = element.ownerDocument.defaultView!.getComputedStyle(parent);
    const box = parent.getBoundingClientRect();
    if (/(auto|scroll|hidden|clip)/.test(style.overflowY)) { top = Math.max(top, box.top); bottom = Math.min(bottom, box.bottom); }
    if (/(auto|scroll|hidden|clip)/.test(style.overflowX)) { left = Math.max(left, box.left); right = Math.min(right, box.right); }
    if (parent === root) break;
  }
  return bottom > top && right > left;
}

function scrollRegion(element: HTMLElement, root: HTMLElement, y: boolean) {
  for (let parent = element.parentElement; parent && parent !== root; parent = parent.parentElement) {
    const style = element.ownerDocument.defaultView!.getComputedStyle(parent);
    if (/(auto|scroll)/.test(y ? style.overflowY : style.overflowX)) return parent;
  }
  return null;
}

// Resolve directions against rendered rectangles, not DOM/tab order. This also
// handles toolbars wrapping and the filter column becoming a row on handhelds.
export function navigate(event: GamepadEvent) {
  const button = event.detail.button;
  if (![GamepadButton.DIR_UP, GamepadButton.DIR_DOWN, GamepadButton.DIR_LEFT, GamepadButton.DIR_RIGHT].includes(button)) return;
  const target = event.target as HTMLElement;
  const root = target?.closest<HTMLElement>('[data-dd-navigation]');
  if (!root) return; // Steam keyboard/dropdown overlays own their navigation.
  const candidates = Array.from(root.querySelectorAll<HTMLElement>(controls)).filter(element => {
    if (element.hasAttribute('data-dd-group') || element.matches(':disabled,[aria-disabled="true"],input[type="hidden"]') || element.closest('[hidden],[inert]')) return false;
    const rect = element.getBoundingClientRect();
    const style = element.ownerDocument.defaultView!.getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' &&
      !element.querySelector(controls); // Prefer the actual control over a wrapper.
  });
  const current = candidates.find(element => element === target || element.contains(target)) ||
    candidates.find(element => element === root.ownerDocument.activeElement) ||
    candidates.find(element => element.classList.contains('gpfocus'));
  if (!current) return;
  reveal(current);
  const y = vertical(button), rect = current.getBoundingClientRect();
  const region = scrollRegion(current, root, y);
  let pool = candidates;
  const zone = current.closest<HTMLElement>('[data-dd-zone]');
  if (root.dataset.ddPage === 'settings' && zone) {
    pool = candidates.filter(element => element.closest('[data-dd-zone]') === zone);
    if (y) {
      const forward = button === GamepadButton.DIR_DOWN;
      const inside = pool.some(element => element !== current && (forward ?
        element.getBoundingClientRect().top >= rect.bottom - 2 : element.getBoundingClientRect().bottom <= rect.top + 2));
      if (!inside) {
        const zones = Array.from(root.querySelectorAll<HTMLElement>('[data-dd-zone]'));
        const adjacent = zones[zones.indexOf(zone) + (forward ? 1 : -1)];
        pool = candidates.filter(element => element.closest('[data-dd-zone]') === adjacent && !!adjacent);
        // Enter the edge of the next section even if its controls were scrolled
        // away. Never jump over the tabs to the header's Back button.
        const edge = pool.sort((a, b) => forward ? a.getBoundingClientRect().top - b.getBoundingClientRect().top :
          b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom)[0];
        event.preventDefault(); event.stopPropagation();
        if (edge) focus(edge);
        return;
      }
    }
  }
  let best: HTMLElement | undefined, score = Infinity;
  for (const element of pool) {
    if (element === current) continue;
    if (!visibleRect(element, root) && (!region || scrollRegion(element, root, y) !== region)) continue;
    const next = element.getBoundingClientRect();
    const gap = button === GamepadButton.DIR_DOWN ? next.top - rect.bottom :
      button === GamepadButton.DIR_UP ? rect.top - next.bottom :
      button === GamepadButton.DIR_RIGHT ? next.left - rect.right : rect.left - next.right;
    if (gap < -2) continue; // Down must never select the next button in the same row.
    const cross = y ? Math.max(0, next.left - rect.right, rect.left - next.right) :
      Math.max(0, next.top - rect.bottom, rect.top - next.bottom);
    const alignment = y ? Math.abs(next.left + next.right - rect.left - rect.right) / 2 :
      Math.abs(next.top + next.bottom - rect.top - rect.bottom) / 2;
    // Prefer the same visual row/column even when a toolbar has a wide spacer.
    const sameScroll = region && scrollRegion(element, root, y) === region;
    // Finish traversing a scrollable form/list before escaping to fixed bars.
    // Otherwise an offscreen previous field loses to the visible Back button.
    const distance = (sameScroll ? -2000000 : 0) + (cross > 2 ? 1000000 : 0) + Math.max(0, gap) + cross * 4 + alignment * 0.15;
    if (distance < score) { score = distance; best = element; }
  }
  // Consume boundaries too: falling back to Steam's linear flow would turn
  // Down into Right at the edge and reintroduce the reported issue.
  event.preventDefault(); event.stopPropagation();
  if (best) {
    focus(best);
    const destinationRegion = scrollRegion(best, root, y);
    if (button === GamepadButton.DIR_UP && destinationRegion && !candidates.some(element =>
      element !== best && scrollRegion(element, root, true) === destinationRegion &&
      element.getBoundingClientRect().bottom <= best!.getBoundingClientRect().top + 2)) {
      destinationRegion.scrollTop = 0;
    }
  }
}

export const Spatial = forwardRef<HTMLDivElement, FocusableProps>(function Spatial(props, ref) {
  return <Focusable {...props} ref={ref} data-dd-group onGamepadDirection={event => {
    props.onGamepadDirection?.(event);
    if (!event.defaultPrevented) navigate(event);
  }} />;
});
