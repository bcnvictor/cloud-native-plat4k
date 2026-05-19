interface HexLogoProps {
  size?: number;
}

export const HexLogo = ({ size = 16 }: HexLogoProps) => (
  <svg viewBox="0 0 16 16" style={{ width: size, height: size, fill: 'white' }} aria-hidden="true">
    <path d="M8 1L14 4.5V11.5L8 15L2 11.5V4.5L8 1Z" />
  </svg>
);
