// ignore: deprecated_member_use
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:homecue_mobile/main.dart';

void main() {
  testWidgets('UPI demo produces a labelled receipt', (tester) async {
    String? receipt;
    await tester.pumpWidget(MaterialApp(
        home: Builder(
            builder: (context) => Scaffold(
                body: TextButton(
                    onPressed: () async {
                      receipt = await showDialog<String>(
                          context: context,
                          builder: (_) =>
                              const DemoPaymentDialog(total: 15498));
                    },
                    child: const Text('Checkout'))))));
    await tester.tap(find.text('Checkout'));
    await tester.pumpAndSettle();
    expect(find.text('homecue-demo@example'), findsOneWidget);
    await tester.tap(find.text('UPI'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Credit / debit card').last);
    await tester.pumpAndSettle();
    expect(find.text('4242 4242 4242 4242'), findsOneWidget);
    await tester.tap(find.text('Credit / debit card'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('UPI').last);
    await tester.pumpAndSettle();
    expect(find.text('homecue-demo@example'), findsOneWidget);
    await tester.tap(find.text('Complete demo payment'));
    await tester.pumpAndSettle();
    expect(receipt, 'UPI · Google Pay');
  });

  testWidgets('EMI keeps total exact and declined payment stays open',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: DemoPaymentDialog(total: 20087))));
    await tester.tap(find.text('UPI'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('EMI').last);
    await tester.pumpAndSettle();
    expect(
        find.text(
            '2 payments of ₹6696 + final payment of ₹6695. Total ₹20087.'),
        findsOneWidget);
    await tester.ensureVisible(find.text('Successful payment'));
    await tester.tap(find.text('Successful payment'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Declined').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Complete demo payment'));
    await tester.pumpAndSettle();
    expect(
        find.text(
            'Demo payment declined. Choose another method or switch to successful and retry.'),
        findsOneWidget);
    expect(find.byType(DemoPaymentDialog), findsOneWidget);
  });
}
