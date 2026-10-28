import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

/// Contents of the QR code shown by the desktop tray app.
class PairingCode {
  PairingCode({required this.server, required this.pairId, required this.token, this.firebase});

  final String server;
  final String pairId;
  final String token;

  /// Public options of the server owner's Firebase project (api_key, app_id, project_id,
  /// sender_id). Null for servers that don't send them.
  final Map<String, String>? firebase;

  static const firebaseKeys = ['api_key', 'app_id', 'project_id', 'sender_id'];

  /// Returns null when the scanned text isn't an AE Buzz pairing code.
  static PairingCode? tryParse(String? raw) {
    if (raw == null) return null;
    try {
      final data = jsonDecode(raw);
      if (data is! Map || data['v'] != 1) return null;
      final server = data['server'], pair = data['pair'], token = data['token'];
      if (server is! String || pair is! String || token is! String) return null;
      Map<String, String>? firebase;
      final fb = data['fb'];
      if (fb is Map && firebaseKeys.every((k) => fb[k] is String && (fb[k] as String).isNotEmpty)) {
        firebase = {for (final k in firebaseKeys) k: fb[k] as String};
      }
      return PairingCode(
        server: server.replaceAll(RegExp(r'/+$'), ''),
        pairId: pair,
        token: token,
        firebase: firebase,
      );
    } on FormatException {
      return null;
    }
  }
}

class Pairing {
  Pairing({required this.server, required this.pairId, required this.phoneSecret});

  final String server;
  final String pairId;
  final String phoneSecret;
}

class RelayException implements Exception {
  RelayException(this.message);
  final String message;
  @override
  String toString() => message;
}

/// Pairing state (secure storage) and calls to the relay server.
class Relay {
  static const _storage = FlutterSecureStorage();

  static Future<Pairing?> load() async {
    final values = await _storage.readAll();
    final server = values['server'], pairId = values['pair_id'], secret = values['phone_secret'];
    if (server == null || pairId == null || secret == null) return null;
    return Pairing(server: server, pairId: pairId, phoneSecret: secret);
  }

  static Future<Pairing> claim(PairingCode code, String fcmToken) async {
    final http.Response r;
    try {
      r = await http
          .post(
            Uri.parse('${code.server}/pairings/${code.pairId}/claim'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'pair_token': code.token, 'fcm_token': fcmToken}),
          )
          .timeout(const Duration(seconds: 15));
    } on Exception catch (e) {
      throw RelayException("Couldn't reach the relay server at ${code.server}.\n$e");
    }
    switch (r.statusCode) {
      case 200:
        break;
      case 409:
        throw RelayException('This code was already used. Show a new QR code on the laptop.');
      case 410:
        throw RelayException('This code expired. Show a new QR code on the laptop.');
      default:
        throw RelayException('Pairing failed (HTTP ${r.statusCode}).');
    }
    final secret = (jsonDecode(r.body) as Map)['phone_secret'] as String;
    final pairing = Pairing(server: code.server, pairId: code.pairId, phoneSecret: secret);
    await _storage.write(key: 'server', value: pairing.server);
    await _storage.write(key: 'pair_id', value: pairing.pairId);
    await _storage.write(key: 'phone_secret', value: pairing.phoneSecret);
    return pairing;
  }

  /// Tells the server this phone's current FCM token (push target).
  static Future<void> updateFcmToken(Pairing p, String token) async {
    try {
      await http
          .put(
            Uri.parse('${p.server}/pairings/${p.pairId}/fcm-token'),
            headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ${p.phoneSecret}'},
            body: jsonEncode({'fcm_token': token}),
          )
          .timeout(const Duration(seconds: 15));
    } on Exception {
      // Best effort; the next app start retries with the current token.
    }
  }

  /// Unpairs on the server when reachable, and always forgets the pairing locally.
  static Future<void> unpair(Pairing p) async {
    try {
      await http
          .delete(
            Uri.parse('${p.server}/pairings/${p.pairId}'),
            headers: {'Authorization': 'Bearer ${p.phoneSecret}'},
          )
          .timeout(const Duration(seconds: 15));
    } on Exception {
      // Server unreachable: the laptop will see 410 once its pairing is gone or re-paired.
    }
    await _storage.deleteAll();
  }
}

/// Recently forwarded titles, newest first. Best effort: Android only lets the app see
/// notifications that arrive while it's open or that the user taps.
class History {
  static const _key = 'history';
  static const _max = 50;
  static final _prefs = SharedPreferencesAsync();

  static Future<List<String>> load() async => await _prefs.getStringList(_key) ?? [];

  static Future<void> add(String title) async {
    final entry = '${DateTime.now().toIso8601String()}|$title';
    final items = [entry, ...await load()];
    await _prefs.setStringList(_key, items.take(_max).toList());
  }

  static Future<void> clear() => _prefs.remove(_key);
}
