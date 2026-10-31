import { ICON_PATHS, LOGO_SVG } from './icon-paths';
import avatar0 from '@/assets/avatar-0.svg';
import avatar1 from '@/assets/avatar-1.svg';
import avatar2 from '@/assets/avatar-2.svg';
import avatar3 from '@/assets/avatar-3.svg';
import avatar4 from '@/assets/avatar-4.svg';
import avatar5 from '@/assets/avatar-5.svg';

const AVATARS = [avatar0, avatar1, avatar2, avatar3, avatar4, avatar5];

/** Same SVG markup as the prototype's icon() helper. */
export function Icon({ name, size = 18 }: { name: string; size?: number }) {
  return (
    <svg
      className={`icon icon-${name}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      dangerouslySetInnerHTML={{ __html: ICON_PATHS[name] || ICON_PATHS.grid }}
    />
  );
}

export function Avatar({ index = 0, size = 36 }: { index?: number; size?: number }) {
  const i = (((Number(index) || 0) % 6) + 6) % 6;
  return (
    <img
      className="avatar"
      src={AVATARS[i]}
      width={size}
      height={size}
      alt=""
      style={{ width: size, height: size, flexShrink: 0, borderRadius: '50%', objectFit: 'cover' }}
    />
  );
}

/** The prototype injects the logo SVG directly into its parent; use as `dangerouslySetInnerHTML={logoHtml}`. */
export const logoHtml = { __html: LOGO_SVG };
