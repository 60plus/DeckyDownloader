import icon from '../assets/icon.png';

export function Icon({ size = 24 }: { size?: number }) {
  return <img src={icon} width={size} height={size} alt="" aria-hidden="true" draggable={false}
    style={{ display: 'block', objectFit: 'contain', flexShrink: 0 }} />;
}
