# konfigurace node instance

## Hlavní konfigurace

je uložena v souboru `~/muj-node-config.js` který je nastavován managerem instancí, takže nezasahovat

Tento soubor vytváří z `runtime` property běhovou proměnnou `global.get('jb_cfg)` dále jen **jb_cfg**

## Další konfigurace vs `global.get('jb_cfg')`

`global.get('jb_cfg')` dále jen **jb_cfg**

Je možné přidat do adresáře `~/.nodered_my_cfg/` soubory které ovlivní chování nebo **jb_cfg**


### `my_cfg_init.json`

je json objekt ze kterého se aktuálně zpracovává property:

```json
{
    "title":"nazev instance", // toto se propíše do jb_cfg.title a záhlaví admin node-red (po restartu node-red, pokud změníme)
}
```

Samozřejmě musí mít práva a ownering pro instanci node-red, jinak to z instance nezměníme

### `my_cfg.json`

je json objekt který se přímo parsuje do **jb_cfg** a přepíše jeho hodnoty/property, příklad

```json
{
    "__v__":"2.0.0",
    "mqtt": {
        "pro"  : "firma",
        "type" : "typDevice",
        "user" : "jmeno",
        "pwd"  : "heslo",
        "host" : "server.cz",
        "port" : 12345
    },
    "zlklApi" : {
        "__create__" : true,
        "noderedsys":{
            "__create__" : true,
            "http":"apikey1",
            "comm":null
        },
        "zlklmqttdevs":{
            "__create__" : true,
            "http":"apikey2",
            "comm":null
        },
        "tof_node_api" : {
            "__create__" : true,
            "http": "apikey3",
            "comm":null
        }
    }
}
```

### `my_loader.js`

Pokud existuje tak musí exportem vrátit seznam knihoven které budou umístěny do `global.get('jb_cfg').libs` dále jen **libs**

Pokud není definován tak je **libs** prázdný objekt `{}` toto lze ovlivnit dále

#### `libs.list`

Je seznam knihoven které se přidají do objektu **libs**

Je to seznam kde syntax je: `"nazevKnihovny=cestaKeKnihovne"`, cesta se použije do require

Je tu jedna výjimka a to název **root** pokud použijeme tento tak se exporty parsují na **libs** přímo

Jinak se název stává property v **libs** a exporty jeho hodnotami

Příklad `libs.list`:

```js
root=/opt/hlKnihovny/my_root_lib.js,
crypto=/opt/jsLibs/cryptoLib.js,
```

**!!! Pozor aby tento list fungoval, musí být v home definován soubor (klidně prázdný) `~/add_js_libs_to_node_red` !!!**  
Pokud není definován tak se tento list ignoruje

