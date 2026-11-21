// ignore: deprecated_member_use
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:homecue_mobile/main.dart';

void main() {
  test('Custom quotes match Starter and Family and increase per option', () {
    const options=[{'id':'task','setup_inr':5000,'monthly_inr':150},{'id':'orientation','setup_inr':5000,'monthly_inr':150},{'id':'night','setup_inr':2000,'monthly_inr':100},{'id':'entrance','setup_inr':2000,'monthly_inr':100},{'id':'escalation','setup_inr':2000,'monthly_inr':100}];
    final starter=customTotals(options,['task','orientation'],1,1,false,{});
    expect(starter['monthly'],499);expect(starter['setup'],14999);expect(starter['total'],15498);
    final family=customTotals(options,options.map((o)=>o['id'] as String).toList(),3,3,false,{});
    expect(family['monthly'],999);expect(family['setup'],24999);
    expect(customTotals(options,['task'],1,1,false,{})['monthly'],349);
    expect(customTotals(options,['task','orientation'],1,1,true,{})['total'],20087);
  });
  testWidgets('Custom plan requires selection and retains choices during review', (tester) async {
    await tester.pumpWidget(const MaterialApp(home:Scaffold(body:CustomPlanDialog(options:[
      {'id':'task','name':'Task guidance','benefit':'Review a routine','availability':'Lab prototype'},
      {'id':'orientation','name':'Orientation and routines','benefit':'Time cues','availability':'Planned display'},
    ]))));
    expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton,'Review configuration')).onPressed,isNull);
    await tester.tap(find.text('Task guidance'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Review configuration'));
    await tester.pumpAndSettle();
    expect(find.text('✓ Task guidance'),findsOneWidget);
    expect(find.text('✓ Orientation and routines'),findsNothing);
    await tester.tap(find.text('Edit options'));
    await tester.pumpAndSettle();
    expect(tester.widget<CheckboxListTile>(find.byType(CheckboxListTile).first).value,isTrue);
  });
}
