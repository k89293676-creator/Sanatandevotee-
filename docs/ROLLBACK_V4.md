# Rollback V4
1. git checkout pre-v4
2. Restore DB: copy backups/pre-v4/factory.db to data/factory.db
3. Redeploy previous Worker: npx wrangler rollback (or redeploy from pre-v4 relay)
4. Re-enable graph_api backend only if Meta secrets not retired (after U10 they are gone -> need new creds).
5. Restore Supabase tables from backups/pre-v4/*.json if exported.