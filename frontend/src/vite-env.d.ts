/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_SIP_MODE?: string;
  readonly VITE_SIP_WSS_URL?: string;
  readonly VITE_SIP_DOMAIN?: string;
  readonly VITE_SIP_URI?: string;
  readonly VITE_SIP_USERNAME?: string;
  readonly VITE_SIP_PASSWORD?: string;
  readonly VITE_SIP_DISPLAY_NAME?: string;
  readonly VITE_SIP_AUTHORIZATION_USERNAME?: string;
  readonly VITE_SIP_CONTACT_URI?: string;
  readonly VITE_SIP_DIAL_FORMAT?: string;
  readonly VITE_SIP_DIAL_PREFIX?: string;
  readonly VITE_DEFAULT_COUNTRY_CODE?: string;
  readonly VITE_STUN_URL?: string;
  readonly VITE_TURN_URL?: string;
  readonly VITE_TURN_USERNAME?: string;
  readonly VITE_TURN_PASSWORD?: string;
}
