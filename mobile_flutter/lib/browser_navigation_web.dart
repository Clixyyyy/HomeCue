import 'dart:js_interop';

@JS('window.location.replace')
external void _replace(JSString url);
void redirectBrowser(String url) => _replace(url.toJS);
