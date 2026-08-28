import { Pool } from "pg";

// Reuse one pool across hot reloads in development.
const globalForPool = globalThis as unknown as { pgPool?: Pool };

export const pool =
  globalForPool.pgPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    max: 5,
    ssl: process.env.DATABASE_SSL === "false" ? undefined : { rejectUnauthorized: true },
  });

if (process.env.NODE_ENV !== "production") {
  globalForPool.pgPool = pool;
}
