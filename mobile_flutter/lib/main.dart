import 'dart:convert';
import 'browser_navigation_stub.dart'
    if (dart.library.js_interop) 'browser_navigation_web.dart';
import 'dart:async';
import 'package:flutter/foundation.dart';
// Keep compatibility with Flutter versions before the Material UI package split.
// ignore: deprecated_member_use
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// HomeCue caregiver mobile client. Uses the SAME API as the website.
/// This app doesn't operate physical devices, call emergency services, or diagnose health conditions.
void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const HomeCueApp());
}

const kInk = Color(0xFF111111);
const kSoft = Color(0xFFF3F3F3);
const kSecondary = Color(0xFF626262);

class ApiException implements Exception {
  final String message;
  ApiException(this.message);
  @override
  String toString() => message;
}

class Api {
  final String baseUrl;
  final String? token;
  Api(this.baseUrl, this.token);

  Future<dynamic> send(String endpoint,
      {String method = 'GET', Object? body}) async {
    final url =
        Uri.parse('${baseUrl.replaceAll(RegExp(r'/$'), '')}/api$endpoint');
    final headers = <String, String>{'Content-Type': 'application/json'};
    if (token != null && token!.isNotEmpty)
      headers['Authorization'] = 'Bearer $token';
    http.Response response;
    final client = http.Client();
    try {
      final request = http.Request(method, url);
      request.headers.addAll(headers);
      if (body != null) request.body = jsonEncode(body);
      final streamed =
          await client.send(request).timeout(const Duration(seconds: 12));
      response = await http.Response.fromStream(streamed)
          .timeout(const Duration(seconds: 12));
    } catch (_) {
      throw ApiException(
          'Server not reachable. Check its address, Wi-Fi and firewall.');
    } finally {
      client.close();
    }
    dynamic data;
    try {
      data = jsonDecode(response.body);
    } catch (_) {
      data = <String, dynamic>{};
    }
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final detail = data is Map ? data['detail'] : null;
      final msg = detail is String
          ? detail
          : detail is List
              ? detail.map((e) => e['msg']).join('; ')
              : 'Request failed (${response.statusCode})';
      throw ApiException(msg);
    }
    return data;
  }
}

class HomeCueApp extends StatefulWidget {
  const HomeCueApp({super.key});
  @override
  State<HomeCueApp> createState() => _HomeCueAppState();
}

class _HomeCueAppState extends State<HomeCueApp> {
  static const storage = FlutterSecureStorage();
  // Browser sessions stay in memory so the local Wi-Fi demo also works over HTTP.
  // Native app credentials continue to use the OS secure store.
  final browserSession = <String, String>{};
  Future<String?> readSetting(String key) async =>
      kIsWeb ? browserSession[key] : storage.read(key: key);
  Future<void> writeSetting(String key, String value) async {
    if (kIsWeb) {
      browserSession[key] = value;
    } else {
      await storage.write(key: key, value: value);
    }
  }

  Future<void> deleteSetting(String key) async {
    if (kIsWeb) {
      browserSession.remove(key);
    } else {
      await storage.delete(key: key);
    }
  }

  String apiUrl =
      const String.fromEnvironment('HOMECUE_API_URL', defaultValue: '');
  final navigatorKey = GlobalKey<NavigatorState>();
  final messengerKey = GlobalKey<ScaffoldMessengerState>();
  Timer? refreshTimer;
  bool syncing = false;
  bool annual = false;
  String token = '';
  String userName = 'Caregiver';
  String message = '';
  Map<String, dynamic>? selectedHome;
  List<dynamic> homes = [];
  List<dynamic> modules = [];
  List<dynamic> events = [];
  List<dynamic> contacts = [];
  List<dynamic> members = [];
  List<dynamic> plans = [];
  List<dynamic> customOptions = [];
  Map<String, dynamic> customPricing = {};
  Map<String, dynamic>? customConfig;
  int tab = 0;
  bool busy = false;
  bool booting = true;
  final emailCtrl = TextEditingController();
  final passwordCtrl = TextEditingController();
  final nameCtrl = TextEditingController(text: 'Caregiver');
  final homeCtrl = TextEditingController(text: 'Family home');
  final cityCtrl = TextEditingController();
  final contactNameCtrl = TextEditingController();
  final contactPhoneCtrl = TextEditingController();
  final memberEmailCtrl = TextEditingController();

  Api get api => Api(apiUrl, token);
  int? get homeId => selectedHome?['id'] as int?;
  String memberRole = 'viewer';
  bool get canEdit => selectedHome?['owner'] == true || memberRole == 'editor';

  @override
  void initState() {
    super.initState();
    if (apiUrl.isEmpty)
      apiUrl = kIsWeb
          ? Uri.base.origin
          : defaultTargetPlatform == TargetPlatform.android
              ? 'http://10.0.2.2:8000'
              : 'http://127.0.0.1:8000';
    restore();
    refreshTimer = Timer.periodic(const Duration(seconds: 10), (_) async {
      if (!mounted || booting || busy || syncing || token.isEmpty) return;
      syncing = true;
      try {
        await loadEverything();
      } catch (_) {
      } finally {
        syncing = false;
      }
    });
  }

  @override
  void dispose() {
    refreshTimer?.cancel();
    for (final c in [
      emailCtrl,
      passwordCtrl,
      nameCtrl,
      homeCtrl,
      cityCtrl,
      contactNameCtrl,
      contactPhoneCtrl,
      memberEmailCtrl
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> restore() async {
    apiUrl = await readSetting('api_url') ?? apiUrl;
    token = await readSetting('user_token') ?? '';
    if (kIsWeb && token.isEmpty) {
      try {
        final session = await Api(apiUrl, null).send('/remote-session');
        token = session['token'] as String;
        await writeSetting('user_token', token);
      } catch (_) {}
    }

    if (token.isNotEmpty) {
      try {
        await loadEverything();
      } catch (e) {
        message = '$e';
        if (RegExp('Invalid or expired|Sign in again', caseSensitive: false)
            .hasMatch('$e')) {
          token = '';
          selectedHome = null;
          await deleteSetting('user_token');
        }
      }
    }
    if (mounted) setState(() => booting = false);
  }

  void feedback(String value) {
    if (!mounted) return;
    setState(() => message = value);
    messengerKey.currentState?.showSnackBar(SnackBar(content: Text(value)));
  }

  Future<void> perform(Future<void> Function() action) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      await action();
    } catch (e) {
      if (RegExp('Invalid or expired|Sign in again', caseSensitive: false)
          .hasMatch('$e')) await logout();
      feedback(e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> login({required bool register}) async {
    if (register && passwordCtrl.text.length < 12) {
      feedback('Use at least 12 characters for a new HomeCue password.');
      return;
    }
    await perform(() async {
      final res = await api.send('/auth/${register ? 'register' : 'login'}',
          method: 'POST',
          body: {
            'email': emailCtrl.text.trim(),
            'password': passwordCtrl.text,
            if (register) 'name': nameCtrl.text.trim(),
          }) as Map<String, dynamic>;
      token = res['token'] as String;
      userName = ((res['user'] as Map)['name']).toString();
      await writeSetting('user_token', token);
      passwordCtrl.clear();
      await loadEverything();
    });
  }

  Future<void> logout() async {
    if (kIsWeb) {
      try {
        final result =
            await Api(apiUrl, null).send('/remote-sign-out', method: 'POST');
        if (result['remote'] == true)
          redirectBrowser(result['sign_in_url'] as String);
      } catch (_) {}
    }
    await deleteSetting('user_token');
    if (mounted)
      setState(() {
        customConfig = null;
        token = '';
        selectedHome = null;
        homes = [];
        events = [];
        modules = [];
        tab = 0;
      });
  }

  Future<void> loadEverything() async {
    final user = await api.send('/me') as Map<String, dynamic>;
    userName = user['name'] as String? ?? 'Caregiver';
    homes = await api.send('/homes') as List<dynamic>;
    if (homes.isEmpty) {
      if (mounted) setState(() => selectedHome = null);
      return;
    }
    final wanted = homeId;
    final basic = homes
            .cast<Map<String, dynamic>>()
            .where((h) => h['id'] == wanted)
            .firstOrNull ??
        homes.first as Map<String, dynamic>;
    selectedHome =
        await api.send('/homes/${basic['id']}') as Map<String, dynamic>;
    await loadTabData();
    if (mounted) setState(() {});
  }

  Future<void> loadTabData() async {
    if (homeId == null) return;
    final id = homeId!;
    final all = await Future.wait([
      api.send('/homes/$id/events?limit=70'),
      api.send('/homes/$id/contacts'),
      api.send('/homes/$id/members'),
      api.send('/plans'),
    ]);
    events = all[0] as List<dynamic>;
    contacts = all[1] as List<dynamic>;
    members = all[2] as List<dynamic>;
    // Member list is scoped to this home; read the logged-in user's role.
    try {
      final me = await api.send('/me') as Map<String, dynamic>;
      memberRole = members
              .cast<Map<String, dynamic>>()
              .firstWhere((m) => m['id'] == me['id'],
                  orElse: () => {'role': 'viewer'})['role']
              ?.toString() ??
          'viewer';
    } catch (_) {
      memberRole = 'viewer';
    }
    plans = (all[3] as Map)['plans'] as List<dynamic>;
    customOptions = (all[3] as Map)['custom_options'] as List<dynamic>? ?? [];
    customPricing = Map<String, dynamic>.from(
        (all[3] as Map)['custom_pricing'] as Map? ?? {});
    final purchase = selectedHome?['purchase'] as Map?;
    if (purchase?['plan_id'] == 'complete') {
      customConfig = {
        'selected': purchase!['modules'],
        'zones': purchase['zones'],
        'caregivers': purchase['caregivers']
      };
    }
    modules = selectedHome?['modules'] as List<dynamic>? ?? [];
  }

  Future<void> createHome() async {
    await perform(() async {
      await api.send('/homes',
          method: 'POST',
          body: {'name': homeCtrl.text.trim(), 'city': cityCtrl.text.trim()});
      await loadEverything();
      feedback('Home created. Add a test event or link your ESP32.');
    });
  }

  Future<void> changeModule(Map<String, dynamic> m, bool enabled) async {
    await perform(() async {
      await api.send('/homes/$homeId/modules/${m['code']}',
          method: 'PUT',
          body: {'enabled': enabled, 'cue_level': m['cue_level']});
      await loadEverything();
      feedback('Setting saved; this does not control hardware.');
    });
  }

  Future<void> addContact() async {
    await perform(() async {
      await api.send('/homes/$homeId/contacts',
          method: 'POST',
          body: {'name': contactNameCtrl.text, 'phone': contactPhoneCtrl.text});
      contactNameCtrl.clear();
      contactPhoneCtrl.clear();
      await loadEverything();
    });
  }

  Future<void> addMember() async {
    await perform(() async {
      await api.send('/homes/$homeId/members',
          method: 'POST',
          body: {'email': memberEmailCtrl.text, 'role': 'viewer'});
      memberEmailCtrl.clear();
      await loadEverything();
    });
  }

  Future<void> demoEvent() async {
    await perform(() async {
      await api.send('/homes/$homeId/demo-event', method: 'POST');
      await loadEverything();
      feedback('DEMO event created — not from a sensor.');
    });
  }

  Future<void> acknowledge(int id) async {
    await perform(() async {
      await api.send('/homes/$homeId/events/$id/ack', method: 'POST');
      await loadEverything();
    });
  }

  Future<void> saveServerUrl(String value) async {
    final trim = value.trim().replaceAll(RegExp(r'/$'), '');
    final uri = Uri.tryParse(trim);
    if (uri == null ||
        !['http', 'https'].contains(uri.scheme) ||
        uri.host.isEmpty ||
        uri.hasQuery ||
        uri.hasFragment) {
      throw ApiException(
          'Enter a full server URL, such as http://192.168.1.5:8000');
    }
    final health = await Api(trim, null).send('/health');
    if (health is! Map || health['ok'] != true)
      throw ApiException('This address is not a HomeCue server.');
    if (trim != apiUrl) {
      await deleteSetting('user_token');
      token = '';
      selectedHome = null;
      homes = [];
      events = [];
      modules = [];
      tab = 0;
    }
    await writeSetting('api_url', trim);
    if (mounted) setState(() => apiUrl = trim);
    feedback('Connected to HomeCue. Use your website account to sign in.');
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
        navigatorKey: navigatorKey,
        scaffoldMessengerKey: messengerKey,
        title: 'HomeCue',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          scaffoldBackgroundColor: const Color(0xFFFAFAFA),
          colorScheme: ColorScheme.fromSeed(
              seedColor: kInk, brightness: Brightness.light),
          textTheme: ThemeData.light().textTheme.apply(fontFamily: 'Roboto'),
          cardTheme: CardThemeData(
              color: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(
                  side: const BorderSide(color: Color(0xFFE4E4E4)),
                  borderRadius: BorderRadius.circular(20))),
          filledButtonTheme: FilledButtonThemeData(
              style: FilledButton.styleFrom(
                  backgroundColor: kInk,
                  foregroundColor: Colors.white,
                  minimumSize: const Size(100, 50))),
          inputDecorationTheme: InputDecorationTheme(
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(13))),
        ),
        home: Scaffold(
            appBar: AppBar(
                elevation: 0,
                backgroundColor: Colors.white,
                title: const Text('homecue.',
                    style: TextStyle(
                        fontWeight: FontWeight.w900,
                        letterSpacing: -1.7,
                        fontSize: 27)),
                actions: [
                  IconButton(
                      onPressed: showSettings,
                      icon: const Icon(Icons.settings_outlined),
                      tooltip: 'Server settings'),
                  if (token.isNotEmpty)
                    IconButton(
                        onPressed: logout,
                        icon: const Icon(Icons.logout),
                        tooltip: 'Sign out')
                ]),
            body: SafeArea(
                child: booting
                    ? const Center(child: CircularProgressIndicator())
                    : token.isEmpty
                        ? authScreen()
                        : selectedHome == null
                            ? createHomeScreen()
                            : appScreen()),
            bottomNavigationBar: token.isNotEmpty && selectedHome != null
                ? NavigationBar(
                    selectedIndex: tab,
                    onDestinationSelected: (value) {
                      setState(() => tab = value);
                    },
                    destinations: const [
                        NavigationDestination(
                            icon: Icon(Icons.home_outlined), label: 'Home'),
                        NavigationDestination(
                            icon: Icon(Icons.history), label: 'Activity'),
                        NavigationDestination(
                            icon: Icon(Icons.tune), label: 'Setup'),
                        NavigationDestination(
                            icon: Icon(Icons.people_outline), label: 'Family'),
                        NavigationDestination(
                            icon: Icon(Icons.sell_outlined), label: 'Plans')
                      ])
                : null));
  }

  Widget wrap(List<Widget> children) => RefreshIndicator(
      onRefresh: () => perform(loadEverything),
      child: ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.fromLTRB(20, 25, 20, 35),
          children: [
            if (busy) const LinearProgressIndicator(),
            if (message.isNotEmpty)
              Padding(
                  padding: const EdgeInsets.only(bottom: 16),
                  child:
                      Text(message, style: const TextStyle(color: kSecondary))),
            ...children,
            const SizedBox(height: 30),
            const Text(
                'Research prototype · Not emergency support · No physical actuation',
                style: TextStyle(color: kSecondary, fontSize: 12))
          ]));
  Widget heading(String eyebrow, String title, String subtitle) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(eyebrow.toUpperCase(),
            style: const TextStyle(
                fontSize: 12,
                color: kSecondary,
                fontWeight: FontWeight.w800,
                letterSpacing: 1.8)),
        const SizedBox(height: 13),
        Text(title,
            style: const TextStyle(
                fontWeight: FontWeight.w900,
                fontSize: 31,
                letterSpacing: -1.2)),
        const SizedBox(height: 9),
        Text(subtitle, style: const TextStyle(color: kSecondary, fontSize: 16)),
        const SizedBox(height: 25)
      ]);
  Widget box(Widget child) => Card(
      margin: const EdgeInsets.only(bottom: 14),
      child: Padding(padding: const EdgeInsets.all(20), child: child));
  Widget field(TextEditingController ctrl, String label,
          {bool secret = false, TextInputType? keyboard}) =>
      Padding(
          padding: const EdgeInsets.only(bottom: 15),
          child: TextField(
              controller: ctrl,
              obscureText: secret,
              keyboardType: keyboard,
              decoration: InputDecoration(labelText: label)));
  Widget authScreen() => wrap([
        heading('HomeCue for families', 'Welcome home.',
            'Sign in to see the same observations as the website.'),
        box(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          field(nameCtrl, 'Name for a new account'),
          field(emailCtrl, 'Email', keyboard: TextInputType.emailAddress),
          field(passwordCtrl, 'Password', secret: true),
          FilledButton(
              onPressed: busy ? null : () => login(register: false),
              child: const Text('Sign in')),
          const SizedBox(height: 9),
          OutlinedButton(
              onPressed: busy ? null : () => login(register: true),
              child: const Text('Create account')),
          const SizedBox(height: 10),
          const Text('For a new account, use at least 12 characters.',
              style: TextStyle(fontSize: 13, color: kSecondary))
        ])),
        box(Text(
            'API: $apiUrl\nThis works with the local FastAPI server. Use Settings to change the address.',
            style: const TextStyle(color: kSecondary)))
      ]);
  Widget createHomeScreen() => wrap([
        heading('Home setup', 'Name your home.',
            'No street address or health details required.'),
        box(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          field(homeCtrl, 'Home name'),
          field(cityCtrl, 'City (optional)'),
          FilledButton(
              onPressed: busy ? null : createHome,
              child: const Text('Create home'))
        ]))
      ]);
  Widget appScreen() {
    if (tab == 0) return overview();
    if (tab == 1) return activity();
    if (tab == 2) return setup();
    if (tab == 3) return family();
    return pricing();
  }

  Widget purchasedPlanCard() {
    final purchase = selectedHome?['purchase'] as Map?;
    return box(
        Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(purchase == null ? 'NO PLAN PURCHASED' : 'PURCHASED · DEMO',
          style: const TextStyle(
              fontSize: 12, fontWeight: FontWeight.bold, color: kSecondary)),
      const SizedBox(height: 12),
      Text(
          purchase == null
              ? 'Choose your HomeCue plan'
              : '${purchase['name']} plan',
          style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
      if (purchase != null) ...[
        const SizedBox(height: 10),
        Text(
            'Purchased: ${DateTime.parse(purchase['purchased_at'] as String).toLocal().toString().split(' ').first}'),
        Text(
            '${purchase['zones']} home zones · ${purchase['caregivers']} caregiver accounts'),
        const SizedBox(height: 12),
        const Text('Available with your plan',
            style: TextStyle(fontWeight: FontWeight.bold)),
        ...modules.where((m) => m['included'] == true).map((m) => Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text('✓ ${m['label']}'))),
        const SizedBox(height: 12),
        const Text(
            'Demo purchase saved. No real payment was collected. Hardware and planned features require separate setup.',
            style: TextStyle(color: kSecondary, fontSize: 12)),
      ] else
        const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text(
                'Purchase a demo plan to make its included options available in Setup.')),
      const SizedBox(height: 14),
      OutlinedButton(
          onPressed: () => setState(() => tab = 4),
          child: Text(purchase == null ? 'Choose plan' : 'View packages')),
    ]));
  }

  Future<bool> recordPlanPurchase(
      String planId, String payment, String requestId,
      {Map<String, dynamic>? configuration}) async {
    var saved = false;
    await perform(() async {
      await api.send('/homes/$homeId/purchases', method: 'POST', body: {
        'request_id': requestId,
        'plan_id': planId,
        'period': annual ? 'annual' : 'monthly',
        'payment_method': payment,
        if (configuration != null) 'modules': configuration['selected'],
        if (configuration != null) 'zones': configuration['zones'],
        if (configuration != null) 'caregivers': configuration['caregivers'],
      });
      await loadEverything();
      saved = true;
    });
    return saved;
  }

  Widget overview() => wrap([
        heading('MY HOME', 'Hi, $userName.',
            'A simple view of your connected HomeCue prototype.'),
        purchasedPlanCard(),
        box(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(selectedHome?['name'] ?? 'Home',
              style:
                  const TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Chip(
              label: Text(selectedHome?['hardware_connected'] == true
                  ? 'ESP32 seen recently'
                  : 'ESP32 not connected')),
          const SizedBox(height: 15),
          Text(
              '${modules.where((m) => m['included'] == true).length} included modules  ·  ${events.length} recent observations',
              style: const TextStyle(color: kSecondary))
        ])),
        const Text('Modules',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        ...modules.map((m) => box(ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text('${m['label']}',
                style: const TextStyle(fontWeight: FontWeight.w700)),
            subtitle: Text(m['included'] == true
                ? 'Included · Preference: ${m['enabled'] == true ? 'On' : 'Off'} · Cue level ${m['cue_level']}'
                : 'Not included in your plan'),
            trailing: const Icon(Icons.chevron_right)))),
        const SizedBox(height: 12),
        const Text('Recent activity',
            style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        if (events.isEmpty) box(const Text('No sensor events yet.')),
        ...events.take(3).map(eventTile),
        const SizedBox(height: 16),
        const Text(
            'This is a test system. Do not use it as the only way to keep someone safe.',
            style: TextStyle(color: kSecondary))
      ]);
  Widget eventTile(dynamic e) {
    final demo = e['source'] == 'demo';
    return box(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Chip(
            label: Text(demo ? 'DEMO' : 'DEVICE'),
            backgroundColor: demo ? const Color(0xFFFFE9BE) : kSoft),
        const SizedBox(width: 9),
        Expanded(
            child: Text('${e['module']} · ${e['kind']}',
                style: const TextStyle(fontWeight: FontWeight.w800)))
      ]),
      const SizedBox(height: 7),
      Text('${e['message']}'),
      const SizedBox(height: 9),
      Text('${e['created_at']}',
          style: const TextStyle(color: kSecondary, fontSize: 12)),
      if (e['acknowledged'] != true)
        Align(
            alignment: Alignment.centerRight,
            child: TextButton(
                onPressed:
                    busy || !canEdit ? null : () => acknowledge(e['id'] as int),
                child: const Text('Acknowledge')))
    ]));
  }

  Widget activity() => wrap([
        heading('ACTIVITY', 'Recent events.',
            'The same events are visible on your website.'),
        FilledButton.tonal(
            onPressed: busy ? null : demoEvent,
            child: const Text('Create clearly labelled demo event')),
        const SizedBox(height: 13),
        if (events.isEmpty)
          box(const Text(
              'No events yet. ESP32 observations will appear here.')),
        ...events.map(eventTile)
      ]);
  Widget setup() => wrap([
        heading('HOME SETUP', 'Simple preferences.',
            'Saved on the backend. They do not remotely switch hardware.'),
        ...modules.map((m) =>
            box(Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${m['label']}',
                  style: const TextStyle(
                      fontSize: 19, fontWeight: FontWeight.w800)),
              const SizedBox(height: 9),
              SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Preference enabled'),
                  subtitle: Text(m['included'] == true
                      ? 'Included · Cue level ${m['cue_level']}'
                      : 'Not included in your plan'),
                  value: m['enabled'] == true,
                  onChanged: busy || !canEdit || m['included'] != true
                      ? null
                      : (v) => changeModule(m as Map<String, dynamic>, v))
            ]))),
        box(const Text(
            'ESP32 setup: generate a device token once from Website → My Home → Home setup, then paste it into firmware secrets.h. The app never stores device credentials.'))
      ]);
  Widget family() => wrap([
        heading('CARE CIRCLE', 'Family access.',
            'Keep only trusted caregivers in the account.'),
        const Text('Signed-in caregivers',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 19)),
        ...members.map((m) => box(ListTile(
            title: Text('${m['name']}'),
            subtitle: Text('${m['email']} · ${m['role']}')))),
        if (selectedHome?['owner'] == true)
          box(Column(children: [
            field(memberEmailCtrl, 'Registered caregiver email'),
            FilledButton(
                onPressed: busy ||
                        members.length >=
                            ((selectedHome?['purchase'] as Map?)?['caregivers']
                                    as int? ??
                                0)
                    ? null
                    : addMember,
                child: const Text('Grant read-only access')),
            const Text('The caregiver needs their own HomeCue account first.',
                style: TextStyle(color: kSecondary, fontSize: 12))
          ])),
        const SizedBox(height: 19),
        const Text('Trusted contacts (no SMS enabled)',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 19)),
        ...contacts.map((m) => box(ListTile(
            title: Text('${m['name']}'), subtitle: Text('${m['phone']}')))),
        if (canEdit)
          box(Column(children: [
            field(contactNameCtrl, 'Contact name'),
            field(contactPhoneCtrl, 'Phone (optional)'),
            FilledButton(
                onPressed: busy ? null : addContact,
                child: const Text('Save contact'))
          ]))
      ]);
  List<String> benefits(String id) => switch (id) {
        'starter' => [
            'One guidance zone for a familiar routine.',
            'One caregiver account to review observations.',
            'A smaller setup to start exploring home support.'
          ],
        'family' => [
            'Orientation and a task station in one package.',
            'Share the experience with up to three caregivers.',
            'Explore planned night and entrance awareness.'
          ],
        _ => [
            'Plan coverage across up to five home zones.',
            'Choose more configurable cues for your routines.',
            'Tailor installation and planned support to your home.'
          ],
      };
  int monthlyPrice(dynamic plan) => annual
      ? ((plan['monthly_inr'] as num) * .85).round()
      : (plan['monthly_inr'] as num).toInt();
  Widget pricing() => wrap([
        heading('PACKAGES', 'Choose your HomeCue.',
            'The same packages and prices as the website. Try a demo purchase.'),
        purchasedPlanCard(),
        SegmentedButton<bool>(segments: const [
          ButtonSegment(value: false, label: Text('Monthly')),
          ButtonSegment(value: true, label: Text('Annual −15%'))
        ], selected: {
          annual
        }, onSelectionChanged: (v) => setState(() => annual = v.first)),
        const SizedBox(height: 20),
        ...plans.map((m) => box(Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('${m['name']}',
                      style: const TextStyle(
                          fontWeight: FontWeight.w800, fontSize: 24)),
                  const SizedBox(height: 12),
                  Text(
                      m['id'] == 'complete'
                          ? 'Build your price'
                          : '₹${monthlyPrice(m)} / month',
                      style: const TextStyle(
                          fontWeight: FontWeight.w900, fontSize: 30)),
                  Text(
                      m['id'] == 'complete'
                          ? 'Based on your selected options'
                          : annual
                              ? 'Estimated annual rate'
                              : 'Proposed monthly rate',
                      style: const TextStyle(color: kSecondary)),
                  const SizedBox(height: 16),
                  const Text('What you gain',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                  ...benefits('${m['id']}').map((f) => Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: Text('✓  $f'))),
                  const SizedBox(height: 12),
                  ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('Package inclusions'),
                      children: (m['features'] as List)
                          .map((f) => ListTile(title: Text('$f')))
                          .toList()),
                  Text(
                      'One-time setup: ${m['setup_from_inr'] == null ? 'Build your price' : 'from ₹${m['setup_from_inr']}'}'),
                  const SizedBox(height: 16),
                  FilledButton(
                      onPressed: busy || selectedHome?['owner'] != true
                          ? null
                          : () => showCheckout(m),
                      child: Text(m['id'] == 'complete'
                          ? 'Customize Complete'
                          : 'Buy ${m['name']}')),
                ]))),
        const Text(
            'Demo store · No payment is taken and no hardware is ordered. Planned features need further development.',
            style: TextStyle(color: kSecondary)),
      ]);
  Future<void> showCheckout(dynamic plan) async {
    if (busy || selectedHome?['owner'] != true) return;
    final purchaseRequest = 'app-${DateTime.now().microsecondsSinceEpoch}';
    final dialogContext = navigatorKey.currentContext;
    if (dialogContext == null) return;
    if (plan['id'] == 'complete') {
      final result = await showDialog<Map<String, dynamic>>(
          context: dialogContext,
          builder: (_) => CustomPlanDialog(
              options: customOptions,
              initial: customConfig,
              pricing: customPricing,
              annual: annual));
      if (result == null || !mounted) return;
      final paymentContext = navigatorKey.currentContext;
      if (paymentContext == null) return;
      final totals = customTotals(
          customOptions,
          (result['selected'] as List).cast<String>(),
          result['zones'] as int,
          result['caregivers'] as int,
          annual,
          customPricing);
      final payment = await showDialog<String>(
          context: paymentContext,
          builder: (_) => DemoPaymentDialog(total: totals['total']!));
      if (payment == null || !mounted) return;
      final method = payment.startsWith('UPI')
          ? 'upi'
          : payment.startsWith('EMI')
              ? 'emi'
              : 'card';
      if (!await recordPlanPurchase('complete', method, purchaseRequest,
          configuration: result)) return;
      customConfig = result;
      final receiptContext = navigatorKey.currentContext;
      if (receiptContext == null) return;
      final ids = (result['selected'] as List).cast<String>();
      final names = customOptions
          .where((o) => ids.contains(o['id']))
          .map((o) => o['name'])
          .join('\n• ');
      await showDialog<void>(
          context: receiptContext,
          builder: (ctx) => AlertDialog(
                  title: const Text('Custom configuration ready'),
                  content: SingleChildScrollView(
                      child: Text(
                          'Your selected options:\n• $names\n\n${result['zones']} home zones · ${result['caregivers']} caregivers\n\nInitial total: ₹${totals['total']}. Payment: $payment. Demo purchase saved. These options are now available in Setup. No real payment was collected.')),
                  actions: [
                    FilledButton(
                        onPressed: () => Navigator.pop(ctx),
                        child: const Text('Done'))
                  ]));
      return;
    }
    final service = monthlyPrice(plan) * (annual ? 12 : 1);
    final setup = plan['setup_from_inr'] as int?;
    final confirmed = await showDialog<bool>(
        context: dialogContext,
        builder: (ctx) => AlertDialog(
              title: Text('${plan['name']} package'),
              content: SingleChildScrollView(
                  child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                    ...benefits('${plan['id']}').map((b) => Padding(
                        padding: const EdgeInsets.only(bottom: 10),
                        child: Text('✓ $b'))),
                    const Divider(),
                    Text('${annual ? 'Annual' : 'Monthly'} service: ₹$service'),
                    Text(
                        'One-time setup: ${setup == null ? 'Build your price' : 'from ₹$setup'}'),
                    const SizedBox(height: 16),
                    Text(
                        setup == null
                            ? 'Custom total — installation quote required'
                            : 'Estimated initial total: ₹${setup + service}',
                        style: const TextStyle(
                            fontWeight: FontWeight.bold, fontSize: 20)),
                    const SizedBox(height: 12),
                    const Text(
                        'Demo only. No payment or fulfilment. Final installation cost and taxes are not included.'),
                  ])),
              actions: [
                TextButton(
                    onPressed: () => Navigator.pop(ctx, false),
                    child: const Text('Back')),
                FilledButton(
                    onPressed: () => Navigator.pop(ctx, true),
                    child: const Text('Place demo order'))
              ],
            ));
    if (confirmed != true || !mounted) return;
    final nextContext = navigatorKey.currentContext;
    if (nextContext == null) return;
    String? payment = 'Custom quote requested';
    if (setup != null) {
      payment = await showDialog<String>(
          context: nextContext,
          builder: (ctx) => DemoPaymentDialog(total: setup + service));
      if (payment == null || !mounted) return;
    }
    final method = payment.startsWith('UPI')
        ? 'upi'
        : payment.startsWith('EMI')
            ? 'emi'
            : 'card';
    if (!await recordPlanPurchase(
        plan['id'] as String, method, purchaseRequest)) return;
    final receiptContext = navigatorKey.currentContext;
    if (receiptContext == null) return;
    await showDialog<void>(
        context: receiptContext,
        builder: (ctx) => AlertDialog(
                title: const Text('Demo order complete'),
                content: Text(
                    'Your ${plan['name']} package walkthrough is complete.\n\nPayment: $payment\n\nSimulated confirmation only. Demo purchase saved on your dashboard. Included options are now available in Setup. No real payment was taken.'),
                actions: [
                  FilledButton(
                      onPressed: () => Navigator.pop(ctx),
                      child: const Text('Done'))
                ]));
  }

  Future<void> showSettings() async {
    final dialogContext = navigatorKey.currentContext;
    if (dialogContext == null) return;
    final controller = TextEditingController(text: apiUrl);
    await showDialog<void>(
        context: dialogContext,
        builder: (context) => AlertDialog(
                title: const Text('Server address'),
                content: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TextField(
                          controller: controller,
                          keyboardType: TextInputType.url,
                          decoration: const InputDecoration(
                              labelText: 'Full backend URL',
                              hintText: 'http://192.168.1.5:8000')),
                      const SizedBox(height: 10),
                      const Text(
                          'Android emulator: http://10.0.2.2:8000\nPhysical phone: http://YOUR_PC_LAN_IP:8000',
                          style: TextStyle(color: kSecondary, fontSize: 12))
                    ]),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Cancel')),
                  FilledButton(
                      onPressed: () async {
                        try {
                          await saveServerUrl(controller.text);
                          if (context.mounted) Navigator.pop(context);
                        } catch (e) {
                          feedback('$e');
                        }
                      },
                      child: const Text('Save'))
                ]));
    controller.dispose();
  }
}

class DemoPaymentDialog extends StatefulWidget {
  final int total;
  const DemoPaymentDialog({super.key, required this.total});
  @override
  State<DemoPaymentDialog> createState() => _DemoPaymentDialogState();
}

class _DemoPaymentDialogState extends State<DemoPaymentDialog> {
  String method = 'UPI';
  String upiApp = 'Google Pay';
  String issuer = 'Demo bank — credit card EMI';
  String outcome = 'Successful payment';
  int months = 3;
  String error = '';
  Widget sample(String label, String value) => Padding(
        padding: const EdgeInsets.only(top: 12),
        child: TextFormField(
            key: ValueKey(label),
            initialValue: value,
            readOnly: true,
            decoration: InputDecoration(labelText: label)),
      );
  @override
  Widget build(BuildContext context) {
    final installment = (widget.total / months).ceil();
    return AlertDialog(
      title: const Text('Choose payment method'),
      content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
              child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                Text('Estimated initial total: ₹${widget.total}',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 12),
                const Text(
                    'DEMO PAYMENT · No money will be collected. Use sample details only.',
                    style: TextStyle(color: kSecondary)),
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                    initialValue: method,
                    decoration:
                        const InputDecoration(labelText: 'Payment method'),
                    items: ['UPI', 'Credit / debit card', 'EMI']
                        .map((m) => DropdownMenuItem(value: m, child: Text(m)))
                        .toList(),
                    onChanged: (v) => setState(() {
                          method = v!;
                          error = '';
                        })),
                const SizedBox(height: 16),
                if (method == 'UPI') ...[
                  DropdownButtonFormField<String>(
                      initialValue: upiApp,
                      decoration:
                          const InputDecoration(labelText: 'Demo UPI app'),
                      items: ['Google Pay', 'PhonePe', 'Paytm', 'Other UPI app']
                          .map(
                              (v) => DropdownMenuItem(value: v, child: Text(v)))
                          .toList(),
                      onChanged: (v) => setState(() => upiApp = v!)),
                  sample('Demo UPI ID', 'homecue-demo@example'),
                  const SizedBox(height: 10),
                  const Text(
                      'Simulates approval only. No app is launched and no UPI PIN is requested.'),
                ],
                if (method == 'Credit / debit card') ...[
                  sample('Demo card number', '4242 4242 4242 4242'),
                  sample('Expiry', '12/30'),
                  sample('CVV', '123'),
                  const SizedBox(height: 10),
                  const Text(
                      'Test card only. Real card entry requires a connected payment provider.'),
                ],
                if (method == 'EMI') ...[
                  DropdownButtonFormField<String>(
                      initialValue: issuer,
                      isExpanded: true,
                      decoration:
                          const InputDecoration(labelText: 'Demo issuer'),
                      items: [
                        'Demo bank — credit card EMI',
                        'Demo finance partner'
                      ]
                          .map(
                              (v) => DropdownMenuItem(value: v, child: Text(v)))
                          .toList(),
                      onChanged: (v) => setState(() => issuer = v!)),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<int>(
                      initialValue: months,
                      decoration: const InputDecoration(labelText: 'Tenure'),
                      items: [3, 6, 9, 12]
                          .map((n) => DropdownMenuItem(
                              value: n, child: Text('$n months')))
                          .toList(),
                      onChanged: (v) => setState(() => months = v!)),
                  const SizedBox(height: 12),
                  Text(
                      '${months - 1} payments of ₹$installment + final payment of ₹${widget.total - installment * (months - 1)}. Total ₹${widget.total}.'),
                  const SizedBox(height: 10),
                  const Text(
                      'Illustrative 0% interest, ₹0 fees. Not a lender offer or approval. Actual rates, taxes and eligibility depend on the provider. Future service renewals are separate.'),
                ],
                const SizedBox(height: 16),
                DropdownButtonFormField<String>(
                    initialValue: outcome,
                    isExpanded: true,
                    decoration: const InputDecoration(
                        labelText: 'Demo payment outcome'),
                    items: ['Successful payment', 'Declined', 'Cancelled']
                        .map((v) => DropdownMenuItem(value: v, child: Text(v)))
                        .toList(),
                    onChanged: (v) => setState(() => outcome = v!)),
                if (error.isNotEmpty)
                  Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(error,
                          style: const TextStyle(color: Colors.red))),
              ]))),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context), child: const Text('Back')),
        FilledButton(
            onPressed: () {
              if (outcome != 'Successful payment') {
                setState(() => error = outcome == 'Declined'
                    ? 'Demo payment declined. Choose another method or switch to successful and retry.'
                    : 'Demo payment cancelled. No charge was made. You can try again.');
                return;
              }
              Navigator.pop(
                  context,
                  method == 'UPI'
                      ? 'UPI · $upiApp'
                      : method == 'EMI'
                          ? 'EMI · $months months · $issuer'
                          : 'Card ending 4242');
            },
            child: const Text('Complete demo payment'))
      ],
    );
  }
}

Map<String, int> customTotals(List<dynamic> options, List<String> selected,
    int zones, int caregivers, bool annual, Map<String, dynamic> rates) {
  final setup = (rates['base_setup_inr'] as int? ?? 4999) +
      options
          .where((o) => selected.contains(o['id']))
          .fold<int>(0, (n, o) => n + (o['setup_inr'] as int? ?? 0)) +
      (zones - 1) * (rates['extra_zone_setup_inr'] as int? ?? 1000) +
      (caregivers - 1) * (rates['extra_caregiver_setup_inr'] as int? ?? 1000);
  final monthly = (rates['base_monthly_inr'] as int? ?? 199) +
      options
          .where((o) => selected.contains(o['id']))
          .fold<int>(0, (n, o) => n + (o['monthly_inr'] as int? ?? 0)) +
      (zones - 1) * (rates['extra_zone_monthly_inr'] as int? ?? 50) +
      (caregivers - 1) * (rates['extra_caregiver_monthly_inr'] as int? ?? 50);
  final rate = annual ? (monthly * .85).round() : monthly;
  final service = rate * (annual ? 12 : 1);
  return {
    'setup': setup,
    'monthly': rate,
    'service': service,
    'total': setup + service
  };
}

class CustomPlanDialog extends StatefulWidget {
  final List<dynamic> options;
  final Map<String, dynamic>? initial;
  final Map<String, dynamic> pricing;
  final bool annual;
  const CustomPlanDialog(
      {super.key,
      required this.options,
      this.initial,
      this.pricing = const {},
      this.annual = false});
  @override
  State<CustomPlanDialog> createState() => _CustomPlanDialogState();
}

class _CustomPlanDialogState extends State<CustomPlanDialog> {
  late Set<String> selected;
  late int zones;
  late int caregivers;
  bool review = false;
  @override
  void initState() {
    super.initState();
    selected = Set<String>.from(widget.initial?['selected'] ?? []);
    zones = widget.initial?['zones'] ?? 1;
    caregivers = widget.initial?['caregivers'] ?? 1;
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(
            review ? 'Review your configuration' : 'Build your own HomeCue'),
        content: SizedBox(
            width: 460,
            child: SingleChildScrollView(
                child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                  if (!review) ...[
                    const Text(
                        'Choose the options that suit your home. Select at least one.'),
                    ...widget.options.map((o) => CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text('${o['name']}'),
                        subtitle: Text(
                            '${o['benefit']}\n${o['availability']}\n₹${o['setup_inr'] ?? 0} setup + ₹${o['monthly_inr'] ?? 0}/month'),
                        value: selected.contains(o['id']),
                        onChanged: (v) => setState(() {
                              if (v == true) {
                                selected.add(o['id'] as String);
                              } else {
                                selected.remove(o['id']);
                              }
                            }))),
                    const SizedBox(height: 16),
                    DropdownButtonFormField<int>(
                        initialValue: zones,
                        decoration:
                            const InputDecoration(labelText: 'Home zones'),
                        items: [1, 2, 3, 4, 5]
                            .map((n) => DropdownMenuItem(
                                value: n,
                                child: Text('$n ${n == 1 ? 'zone' : 'zones'}')))
                            .toList(),
                        onChanged: (n) => setState(() => zones = n!)),
                    const SizedBox(height: 16),
                    DropdownButtonFormField<int>(
                        initialValue: caregivers,
                        decoration: const InputDecoration(
                            labelText: 'Caregiver accounts'),
                        items: [1, 2, 3, 4, 5]
                            .map((n) => DropdownMenuItem(
                                value: n,
                                child: Text(
                                    '$n ${n == 1 ? 'caregiver' : 'caregivers'}')))
                            .toList(),
                        onChanged: (n) => setState(() => caregivers = n!)),
                  ] else ...[
                    ...widget.options
                        .where((o) => selected.contains(o['id']))
                        .map((o) => Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: Text('✓ ${o['name']}'))),
                    Text('$zones home zones · $caregivers caregivers'),
                  ],
                  const SizedBox(height: 20),
                  Text(
                      'Base: ₹${widget.pricing['base_setup_inr'] ?? 4999} setup + ₹${widget.pricing['base_monthly_inr'] ?? 199}/month. Each extra zone or caregiver: ₹1000 setup + ₹50/month. Starter options match ₹499/month + ₹14999 setup. Family options (3 zones, 3 caregivers) match ₹999/month + ₹24999 setup.'),
                  const SizedBox(height: 12),
                  Text(
                      'Setup: ₹${customTotals(widget.options, selected.toList(), zones, caregivers, widget.annual, widget.pricing)['setup']} · ${widget.annual ? 'First year' : 'First month'} service: ₹${customTotals(widget.options, selected.toList(), zones, caregivers, widget.annual, widget.pricing)['service']}'),
                  Text(
                      'Initial total: ₹${customTotals(widget.options, selected.toList(), zones, caregivers, widget.annual, widget.pricing)['total']}',
                      style: const TextStyle(
                          fontWeight: FontWeight.bold, fontSize: 22)),
                  Text(
                      'Renewal: ₹${customTotals(widget.options, selected.toList(), zones, caregivers, widget.annual, widget.pricing)['monthly']}/month${widget.annual ? ', billed annually' : ''}. Demo prices; ₹0 additional taxes/fees in this simulation.',
                      style: TextStyle(color: kSecondary)),
                ]))),
        actions: [
          TextButton(
              onPressed: () {
                if (review) {
                  setState(() => review = false);
                } else {
                  Navigator.pop(context);
                }
              },
              child: Text(review ? 'Edit options' : 'Back')),
          FilledButton(
              onPressed: selected.isEmpty
                  ? null
                  : () {
                      if (!review) {
                        setState(() => review = true);
                      } else {
                        Navigator.pop(context, {
                          'selected': selected.toList(),
                          'zones': zones,
                          'caregivers': caregivers
                        });
                      }
                    },
              child:
                  Text(review ? 'Continue to payment' : 'Review configuration'))
        ],
      );
}
