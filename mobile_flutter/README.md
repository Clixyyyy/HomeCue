# HomeCue caregiver app

## Integrated app on this Mac

The project now includes Android and browser platform files. The app uses the website's existing API, accounts, database, module preferences, contacts and activity feed. Sign in with the same account on both clients. The app checks for updated home data every 10 seconds; pull down to refresh immediately. Website activity currently updates when you reopen or refresh Activity.

Build the browser app with `zsh scripts/BUILD_APP_MAC.command` from the project root. Start/restart the backend with `zsh scripts/START_BACKEND_MAC.command`, then open **http://127.0.0.1:8000/app/**. The website navigation also links to the caregiver app. The browser app uses the same server automatically; a separate Flutter development server can use `--dart-define=HOMECUE_API_URL=http://127.0.0.1:8000`.

For Android, run `flutter run` inside `mobile_flutter` with an Android emulator or device attached and the Android SDK installed. The emulator defaults to `http://10.0.2.2:8000`. For a physical phone, enter your Mac's LAN server address in the app settings and bind the backend to `0.0.0.0`. Server settings verify the HomeCue health endpoint before saving; changing servers signs you out so an old account token isn't sent to the new server.

Packages come from `/api/plans`, with matching monthly and annual estimates, package advantages and demo checkout. Successful demo purchases are saved per home in the shared backend. Both dashboards show the plan, purchase date and included options. No real payment is collected and no paid subscription is activated.

The temporary Flutter SDK used for this session is `/private/tmp/homecue-flutter-sdk`. If macOS clears it, install Flutter and put it in PATH, or set `FLUTTER_BIN` to your Flutter executable before using the build script.

Android development builds include Internet permission and debug-only HTTP access. Production builds require an HTTPS server and your own signing configuration. Android compilation and physical-device testing require the Android SDK and a connected device; they have not been verified on this Mac.

## Android and iPhone browser access

With both phones on the Mac's Wi-Fi, start the server from the project root using `HOMECUE_HOST=0.0.0.0 zsh scripts/START_BACKEND_MAC.command`. Open `http://YOUR_MAC_LAN_IP:8000/app/` in Safari or Chrome and sign in with the website account. The current session address is `http://192.168.0.109:8000/app/`; Wi-Fi addresses can change. Keep the Mac awake. Browser sign-in is held in memory, so reloading the app requires signing in again. Native Android continues to use secure credential storage. Local HTTP access is intended for this demonstration; use HTTPS for deployment.

## Demo payment methods

Website and app checkout support UPI app selection, a read-only test card, and illustrative EMI schedules for 3, 6, 9 or 12 months. EMI installments add up to the estimated initial total; future renewals are separate. Interest and fees are illustrative only. Complete calculates its price from the selected modules, zones and caregivers and proceeds directly to demo UPI/card/EMI payment. Successful, declined and cancelled outcomes can be selected for presentations. Purchase records contain only the plan, included options and payment method. Nothing is charged or sent to a bank; no UPI PIN, real card data or OTP is collected. Live payments require a merchant payment-provider account, server-created payment orders, hosted payment entry and verified server-side payment webhooks.

## Custom package

Choose Customize Complete to select Task guidance, Movement awareness, Entrance awareness, Orientation and routines, and/or Family updates. Both clients load these options and availability notes from `/api/plans`. Select 1–5 home zones and 1–5 caregiver accounts, then review the chosen options before confirming a demo configuration. At least one module is required. Choices remain available when editing during the current session. Confirmed custom configurations are saved as demo purchases. Their selected modules become available in Setup; excluded modules are locked and their saved enabled flags are cleared. Pricing is calculated automatically and no real payment is taken.

## Purchased plans and access

Checkout requires a signed-in home owner and a home. Starter includes task guidance and orientation (one zone, one caregiver including the owner). Family includes all five modules (three zones, three caregivers). Custom Complete includes exactly the selected modules and zone/caregiver counts. The home detail response contains the persisted `purchase` and an `included` flag per module. The server rejects updates to excluded module settings and enforces caregiver account limits. Historical activity stays visible. Planned hardware and notifications remain planned even when included in a demo plan.

`POST /api/homes/{id}/purchases` records demo purchases with an idempotency key. Declined or cancelled UI payments do not call this endpoint. Plan changes replace the current home entitlement set without deleting purchase history. Purchase data persists across backend restarts and app sign-ins. Website pages refresh on navigation/reload; the app refreshes shared data every 10 seconds.

## Custom pricing

The custom quote is calibrated to the preset packages: Task + Orientation with one zone/caregiver equals Starter (₹14,999 setup + ₹499/month); all five options with three zones/caregivers equals Family (₹24,999 setup + ₹999/month). Base setup/service is ₹4,999/₹199. Task and Orientation each add ₹5,000/₹150; Movement, Entrance and Family updates each add ₹2,000/₹100. Each extra zone or caregiver adds ₹1,000 setup + ₹50/month. Annual service gets 15% off; setup remains one-time. The website custom builder is public and displays a sticky live quote; sign-in is required only to save a purchase. Selections persist across refreshes. Payments remain simulated.
