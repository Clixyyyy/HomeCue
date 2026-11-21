#!/bin/zsh
set -eu
cd "$(dirname "$0")/../mobile_flutter"
flutter_bin="${FLUTTER_BIN:-}"
if [[ -z "$flutter_bin" ]]; then
  flutter_bin="$(command -v flutter || true)"
fi
if [[ -z "$flutter_bin" && -x /private/tmp/homecue-flutter-sdk/bin/flutter ]]; then
  flutter_bin=/private/tmp/homecue-flutter-sdk/bin/flutter
fi
if [[ -z "$flutter_bin" ]]; then
  echo "Install Flutter from https://docs.flutter.dev/install, then run this file again."
  exit 1
fi
"$flutter_bin" pub get
"$flutter_bin" build web --base-href /app/ --no-web-resources-cdn
echo "App built. Start the backend, then open http://127.0.0.1:8000/app/"
