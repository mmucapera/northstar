// Active customer config selector.
//
// The customer is chosen via the VITE_CUSTOMER env var (see .env / .env.example),
// defaulting to "customer0". The actual config values are generated at build/dev
// time from config/customers/*.yaml — see scripts/generate-customer-config.ts.

import {
  CUSTOMER_CONFIGS,
  CUSTOMER_IDS,
  type CustomerConfig,
  type CustomerId,
} from "./generated";

function resolveCustomerId(): CustomerId {
  const requested = import.meta.env["VITE_CUSTOMER"] as string | undefined;
  if (requested && (CUSTOMER_IDS as string[]).includes(requested)) {
    return requested as CustomerId;
  }
  if (requested) {
    console.warn(
      `[config] Unknown VITE_CUSTOMER "${requested}" — falling back to "customer0". ` +
        `Known customers: ${CUSTOMER_IDS.join(", ")}`,
    );
  }
  return "customer0";
}

export const CUSTOMER_ID: CustomerId = resolveCustomerId();
export const customerConfig: CustomerConfig = CUSTOMER_CONFIGS[CUSTOMER_ID];

export type { CustomerConfig, CustomerId };
export { CUSTOMER_IDS };
