# ComptaFlow - Prototype vendable (Comptabilité automatisée)

## Démarrage rapide
1. Installer les dépendances :
   - `pip install fastapi uvicorn pydantic python-multipart`
   - `pip install python-dotenv`
   - OCR optionnel : `pip install pytesseract pillow pdf2image`
   - Export XLSX : `pip install openpyxl`
2. OCR cloud (optionnel) :
   - Remplir `OCR_PROVIDER=ocrspace`
   - Remplir `OCRSPACE_API_KEY=...` dans `.env`
3. Paiements SaaS (optionnel) :
   - Remplir `STRIPE_SECRET_KEY=...` dans `.env`
   - Remplir `STRIPE_WEBHOOK_SECRET=...` dans `.env`
   - Remplir `STRIPE_PRICE_STARTER=...`, `STRIPE_PRICE_PRO=...`, `STRIPE_PRICE_ENTERPRISE=...`
   - Installer Stripe SDK : `pip install stripe`
   - URLs retour: `STRIPE_SUCCESS_URL` et `STRIPE_CANCEL_URL`
- Webhooks gérés: `checkout.session.completed`, `customer.subscription.created/updated/deleted`,
  `invoice.payment_succeeded`, `invoice.payment_failed`
2. Lancer l'API :
   - `python -m uvicorn backend.main:app --reload`
3. Ouvrir l'interface :
   - `dashboard/index.html`
4. Se connecter :
   - Email: `admin@comptaflow.fr`
   - Mot de passe: `demo1234`
5. Espace client :
   - Ouvrir `dashboard/client.html` (redirigé automatiquement si rôle client)

## Fonctionnalités démo
- Upload de pièces
- Extraction simulée (OCR + IA placeholder)
- Liste des documents
- Export CSV
- Auth + sessions
- Multi-cabinets (séparation des données)
- Rôles (admin, comptable, client)
- Journal comptable automatique (écritures ACH)
- Règles comptables personnalisables (par cabinet)
- Import bancaire CSV + rapprochement automatique
- Gestion des utilisateurs (admin / comptable / client)
- Métriques abonnements (actifs + statuts)
- Factures Stripe (liste + liens)
- Analytics SaaS (MRR, ARPA, churn)
- Support client (tickets + clôture)
- Base de connaissance (FAQ par cabinet)
- Notifications (messages clients)
- Emails SMTP (relances + messages)
- Workflows (relance pièces + rappel mensuel)
- Sécurité : sessions expirent en 7 jours, logout côté API
- Sécurité : rate-limit basique sur /login + headers HTTP
