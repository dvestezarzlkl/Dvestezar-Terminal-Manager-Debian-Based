# Swap Manager changelog

## v2.5.2

- UX sloupec `Type` v tabulce aktivních swapů je rozšířen z 8 na 10 znaků, takže hodnota `partition` nepřetéká do oddělovače a řádky zůstávají zarovnané.

## v2.5.1

- FIX seznam aktivních swapů používá úplný výstup `swapon --show`, takže zobrazuje swap soubory, swap partition i zram.
- SAFE editační submenu je dostupné pouze pro `TYPE=file`; zram a swap partition se zobrazují pouze informativně.
- UX obecné popisky již neoznačují všechny aktivní swapy jako image.
