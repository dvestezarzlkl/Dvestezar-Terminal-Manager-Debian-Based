var zakladac_id=99; // ID z databáze, 9=je testovací, 8=je tower 2, 5 je tower 1
var opcua_typ='unset_ERR'; // 'test','ch_tower_2','ch_tower_1'
var db_typ='unset_db_ERR'; // text 'fire' zprovozní ostrou databázi, jinak jakýkoliv text zapne testovací

// var title="NODE-RED ZLKL %usr%: "+zakladac_id+" db="+db_typ+", opcua_typ="+opcua_typ;
var title="NODE-RED ZLKL %title%";

module.exports = {
    uiPort: %port%,
    webTitle : title,
    admin_users: [
        {
            username: "%usr%",
            password: "%pwd%",
            permissions: "*"
        }
    ],
    ui_user: null,
    https: null,
    runtime:{
        title:title,
        zakl_id:zakladac_id,
        db_typ:db_typ,
        opcua:opcua_typ,
        errMail:"zednik@zlkl.cz", //zednik@zlkl.cz,putik@zlkl.cz
        errMailFrom:"zednik@zlkl.tech",
        errMailSub:"node-red tst instance %usr% error ("+opcua_typ+")",
    },
    contextStorage: {
       default: "memoryOnly",
       memoryOnly: { module: 'memory' },
       file: { module: 'localfilesystem' },
    }
};