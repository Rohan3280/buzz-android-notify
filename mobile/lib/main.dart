import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import 'relay.dart';

const _native = MethodChannel('aebuzz/native');

@pragma('vm:entry-point')
Future<void> _onBackgroundMessage(RemoteMessage message) async {
  // AeBuzzApplication has already started Firebase natively from the saved options.
  await Firebase.initializeApp();
  final title = message.notification?.title;
  if (title != null) await History.add(title);
}

/// Firebase only exists once a pairing QR has supplied a project's options.
Future<bool> _startFirebaseIfConfigured() async {
  final configured = await _native.invokeMethod<bool>('hasFirebase') ?? false;
  if (!configured) return false;
  await Firebase.initializeApp();
  FirebaseMessaging.onBackgroundMessage(_onBackgroundMessage);
  return true;
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final firebaseReady = await _startFirebaseIfConfigured();
  runApp(AeBuzzApp(firebaseReady: firebaseReady));
}

class AeBuzzApp extends StatelessWidget {
  const AeBuzzApp({super.key, required this.firebaseReady});

  final bool firebaseReady;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AE Buzz',
      theme: ThemeData(colorSchemeSeed: const Color(0xFFD9D72C), useMaterial3: true),
      darkTheme: ThemeData(
        colorSchemeSeed: const Color(0xFFD9D72C),
        brightness: Brightness.dark,
        useMaterial3: true,
      ),
      home: HomeScreen(firebaseReady: firebaseReady),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.firebaseReady});

  final bool firebaseReady;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  Pairing? _pairing;
  List<String> _history = [];
  bool _loading = true;
  bool _messagingStarted = false;
  final _subscriptions = <StreamSubscription>[];

  @override
  void initState() {
    super.initState();
    _init();
  }

  @override
  void dispose() {
    for (final s in _subscriptions) {
      s.cancel();
    }
    super.dispose();
  }

  Future<void> _init() async {
    final pairing = await Relay.load();
    setState(() {
      _pairing = pairing;
      _loading = false;
    });
    await _reloadHistory();
    if (!widget.firebaseReady) return; // set up on first pairing instead

    await _startMessaging();
    if (pairing != null) {
      final token = await _fcmToken();
      if (token != null) await Relay.updateFcmToken(pairing, token);
    }
    final initial = await FirebaseMessaging.instance.getInitialMessage();
    if (initial != null) await _handleTap(initial);
  }

  /// Needs Firebase to be running; called at start-up or right after the first pairing.
  Future<void> _startMessaging() async {
    if (_messagingStarted) return;
    _messagingStarted = true;
    final messaging = FirebaseMessaging.instance;
    await messaging.requestPermission(); // Android 13+ notification permission

    _subscriptions.add(FirebaseMessaging.onMessage.listen((m) async {
      final title = m.notification?.title;
      if (title == null) return;
      await History.add(title);
      await _reloadHistory();
      _snack(title);
    }));
    _subscriptions.add(FirebaseMessaging.onMessageOpenedApp.listen(_handleTap));
    // The classic FCM token API is deprecated in favour of register()/onRegistered,
    // but onRegistered doesn't reliably fire on Android, which left pairing hanging.
    // ignore: deprecated_member_use
    _subscriptions.add(messaging.onTokenRefresh.listen((token) {
      final p = _pairing;
      if (p != null) Relay.updateFcmToken(p, token);
    }));
  }

  /// Points this phone at the Firebase project from the QR. Returns an error message or null.
  Future<String?> _useFirebaseFrom(PairingCode code) async {
    final options = code.firebase;
    if (options == null) {
      if (Firebase.apps.isNotEmpty) return null; // older server; keep the current project
      return "This laptop's AE Buzz server didn't send Firebase settings. "
          'Set AEBUZZ_FIREBASE_APP_CONFIG on the server (see SETUP.md) and show a new code.';
    }
    final result = await _native.invokeMethod<String>('setFirebase', options);
    if (result == 'restart_required') {
      return 'This code uses a different Firebase project. Close AE Buzz completely, '
          'reopen it, and scan a new code.';
    }
    await Firebase.initializeApp();
    FirebaseMessaging.onBackgroundMessage(_onBackgroundMessage);
    await _startMessaging();
    return null;
  }

  Future<void> _handleTap(RemoteMessage message) async {
    final title = message.notification?.title;
    if (title != null) {
      await History.add(title);
      await _reloadHistory();
    }
    final opened = await _native.invokeMethod<bool>('openBuzz') ?? false;
    if (!opened) _snack('Buzz app is not installed on this phone.');
  }

  Future<void> _reloadHistory() async {
    final items = await History.load();
    if (mounted) setState(() => _history = items);
  }

  void _snack(String text) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<String?> _fcmToken() async {
    try {
      // ignore: deprecated_member_use
      return await FirebaseMessaging.instance.getToken().timeout(const Duration(seconds: 20));
    } on Exception {
      return null;
    }
  }

  Future<void> _pair() async {
    final code = await Navigator.of(context).push<PairingCode>(
      MaterialPageRoute(builder: (_) => const ScanScreen()),
    );
    if (code == null || !mounted) return;

    showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => const AlertDialog(
        content: Row(children: [CircularProgressIndicator(), SizedBox(width: 20), Text('Pairing…')]),
      ),
    );
    String? error;
    try {
      final firebaseError = await _useFirebaseFrom(code);
      if (firebaseError != null) throw RelayException(firebaseError);
      final token = await _fcmToken();
      if (token == null) {
        throw RelayException("Couldn't get a push token from Firebase. Check your internet connection and try again.");
      }
      final pairing = await Relay.claim(code, token);
      if (mounted) setState(() => _pairing = pairing);
    } on RelayException catch (e) {
      error = e.message;
    }
    if (!mounted) return;
    Navigator.of(context).pop(); // close "Pairing…"
    if (error == null) {
      _snack('Paired with your laptop.');
    } else {
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text("Couldn't pair"),
          content: Text(error!),
          actions: [TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK'))],
        ),
      );
    }
  }

  Future<void> _unpair() async {
    final p = _pairing;
    if (p == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Unpair this phone?'),
        content: const Text('Your laptop will stop forwarding Buzz notifications here.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Unpair')),
        ],
      ),
    );
    if (confirmed != true) return;
    await Relay.unpair(p);
    await History.clear();
    setState(() {
      _pairing = null;
      _history = [];
    });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    return Scaffold(
      appBar: AppBar(title: const Text('AE Buzz')),
      body: _pairing == null ? _unpairedView() : _pairedView(_pairing!),
    );
  }

  Widget _unpairedView() {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Icon(Icons.notifications_active_outlined, size: 64),
          const SizedBox(height: 16),
          Text(
            'Get your laptop\'s Buzz notifications on this phone.',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          const Text(
            'On the laptop, right-click the AE Buzz tray icon → "Pair phone…", then scan the code.',
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 24),
          FilledButton.icon(
            onPressed: _pair,
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('Scan pairing code'),
          ),
        ],
      ),
    );
  }

  Widget _pairedView(Pairing p) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: ListTile(
            leading: const Icon(Icons.link),
            title: const Text('Paired with your laptop'),
            subtitle: Text(Uri.parse(p.server).host),
          ),
        ),
        Card(
          child: ListTile(
            leading: const Icon(Icons.battery_alert_outlined),
            title: const Text('Make alerts instant'),
            subtitle: const Text('Set Battery to "Unrestricted" for AE Buzz.'),
            trailing: const Icon(Icons.open_in_new),
            onTap: () => _native.invokeMethod('openAppSettings'),
          ),
        ),
        const SizedBox(height: 16),
        Text('Recent', style: Theme.of(context).textTheme.titleSmall),
        if (_history.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text('Nothing yet. Forwarded notifications you open will show up here.'),
          ),
        for (final entry in _history) _historyTile(entry),
        const SizedBox(height: 24),
        OutlinedButton.icon(onPressed: _unpair, icon: const Icon(Icons.link_off), label: const Text('Unpair')),
      ],
    );
  }

  Widget _historyTile(String entry) {
    final sep = entry.indexOf('|');
    final when = DateTime.tryParse(entry.substring(0, sep));
    final title = entry.substring(sep + 1);
    final time = when == null ? '' : TimeOfDay.fromDateTime(when).format(context);
    return ListTile(dense: true, title: Text(title), trailing: Text(time));
  }
}

class ScanScreen extends StatefulWidget {
  const ScanScreen({super.key});

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  bool _done = false;
  DateTime _lastWrongCodeHint = DateTime.fromMillisecondsSinceEpoch(0);

  void _onDetect(BarcodeCapture capture) {
    if (_done) return;
    for (final barcode in capture.barcodes) {
      final code = PairingCode.tryParse(barcode.rawValue);
      if (code != null) {
        _done = true;
        Navigator.of(context).pop(code);
        return;
      }
    }
    // E.g. the QR on Buzz's own Settings → Mobile page. Hint at most every few seconds.
    final now = DateTime.now();
    if (capture.barcodes.isNotEmpty && now.difference(_lastWrongCodeHint).inSeconds >= 4) {
      _lastWrongCodeHint = now;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('That isn\'t an AE Buzz code. Use "Pair phone…" from the AE tray icon on your laptop.'),
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Scan pairing code')),
      body: MobileScanner(onDetect: _onDetect),
    );
  }
}
