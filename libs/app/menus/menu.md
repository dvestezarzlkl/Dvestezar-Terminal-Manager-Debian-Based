# Menu

`menu.py` je hlavní menu které hledá `menu<num>` tzn např 'menu0' 'menu1' menu10'

Pořadí načtení není case sensitive ale abecední, takže pokud chceme pracovat s více menu  
tak se doporučuje formát minimálně s dvěma čísly  
'menu00'

Každé číselné menu (soubor) musí obsahovat:
- stejnojmennou class která je potomkem c_menu
- property `_MENU_MAME_`, toto se zobrazí jako výběrová položka