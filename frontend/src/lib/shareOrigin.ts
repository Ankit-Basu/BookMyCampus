declare const __LAN_ORIGIN__: string

const LOCAL = new Set(['localhost', '127.0.0.1', '[::1]'])

/**
 * The address a QR code should send a phone to. On the live site that's the site itself. When the
 * app runs on this PC as "localhost", a phone can't open that, so use the PC's Wi-Fi address instead.
 */
export function shareOrigin() {
  const lan = typeof __LAN_ORIGIN__ === 'string' ? __LAN_ORIGIN__ : ''
  return LOCAL.has(window.location.hostname) && lan ? lan : window.location.origin
}

/** API path for a QR image whose link should open on a phone. */
export const qrPath = (path: string) => `${path}?origin=${encodeURIComponent(shareOrigin())}`
