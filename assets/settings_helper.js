// version: 1.0.3
const fs = require('fs');
const path = require('path');
const version = '1.0.4';

/**
 * Získá konfiguraci HTTPS pokud je nastavena v jb_cfg
 * @returns {object|null} Objekt s klíčem a certifikátem nebo null pokud není HTTPS nakonfigurováno
 * @version 1.0.0
 * @author dvestezar
 */
function getHttps(jb_cfg){
    console.log('Checking HTTPS configuration...');
    if(!jb_cfg.https){
        console.log('No HTTPS configuration found.');
        return null;
    }
    if(!jb_cfg.https.key){
        console.log('No HTTPS key found in configuration.');
        return null;
    }
    if(!jb_cfg.https.cert){
        console.log('No HTTPS certificate found in configuration.');
        return null;
    }
    console.log('HTTPS configuration found, loading key and certificate...');
    return {
        key: fs.readFileSync(jb_cfg.https.key),
        cert: fs.readFileSync(jb_cfg.https.cert)
    }
}

/**
 * Získá cestu aktuálního usera pod kterým běžíme a přidá k ní složku `.node-red_my_cfg`
 * @param {boolean} homeRoot Pokud je true, vrací pouze home adresář uživatele bez přidání `.node-red_my_cfg`
 * @returns {string} Cesta k `.node-red_my_cfg` v home adresáři uživatele
 * @version 1.0.0
 * @author dvestezar
 */
function getPath(homeRoot=false){
    const homeDir = require('os').homedir();
    let p=homeDir;
    if(!homeRoot){
        p=path.join(homeDir, '.nodered_my_cfg');
    }
    console.log('  > Using configuration path:', p);
    if(!fs.existsSync(p)){
        console.warn('  > Configuration path does not exist');
    }
    return p;
}

/**
 * Načte modul my_loader.js pokud existuje v .node-red složce, modul vrací přímo funkce fo obj libs
 * @returns {object} Objekt s funkcemi z my_loader.js nebo {}
 * @version 1.0.0
 * @author dvestezar
 */
function loadMyLoader(){
    console.log('* Loading additional functions from my_loader.js if exists...');
    const loaderPath = path.join(getPath(), 'my_loader.js');
    let myLoader=null;
    if (fs.existsSync(loaderPath)) {
        console.log(`  + Found my_loader.js at ${loaderPath}, loading...`);
        try {
            myLoader = require(loaderPath);
        } catch(err) {
            console.warn('  - Could not load my_loader.js:', err);
            myLoader = null;
        }
    } else {
        console.log('  - my_loader.js not found at', loaderPath);
        myLoader = null;
    }
    myLoader = myLoader || {};
    myLoader = loadFns(myLoader);
    console.log('* Additional functions loaded:' + Object.keys(myLoader).join(', '));
    return myLoader;
}


function getJson(fullPath){
    fullPath=String(fullPath??'').trim();
    if(!fullPath){
        throw new Error('getJson: fullPath is empty');
    }
    fullPath=path.resolve(fullPath);
    if(!fs.existsSync(fullPath)){
        throw new Error(`getJson: File does not exist: ${fullPath}`);
    }
    try{
        const data = fs.readFileSync(fullPath, 'utf8');
        return JSON.parse(data);
    }catch(err){
        throw new Error(`getJson: Error reading or parsing JSON from ${fullPath}: ${err.message}`);
    }
}

/**
 * vrací objekt jb_cfg a je obohacený o data z my_cfg.json pokud existuje
 * @returns {object} jb_cfg
 * @throws {Error} Pokud nelze načíst nebo parsovat my_cfg.json
 * @version 1.0.1
 * @author dvestezar
 */
function loadMyCFG(){
    const file='my_cfg.json';
    const fileInit='my_cfg_init.json';

    console.log(`* Loading configuration from muj-node-config.js and ${file} if exists...`);
    const homeMain=getPath(true);
    const home=getPath();
    const main=path.join(homeMain,'muj-node-config.js');
    const myCfgPath=path.join(home,file);
    const initCdgPath=path.join(home,fileInit);

    console.log('  - Main configuration file path:', main);
    let jb_cfg=require(main); // toto neodchytáváme, toto je hlavní a důležitý soubor
    // pokud neexistuje runtime, vytvoříme prázdný objekt
    jb_cfg.runtime=jb_cfg.runtime || {};

    // načteme init pokud existuje
    if (fs.existsSync(initCdgPath)) {
        console.log(`  - Found ${fileInit} at ${initCdgPath}, loading initial configuration...`);
        // načtení a parse neodchytáváme, pokud existuje musí být vše v pořádku, jinak se musí opravit a nesmí se node spustit
        const initCfg=getJson(initCdgPath);
        try{
            if(initCfg.title){
                jb_cfg.webTitle=initCfg.title;
                jb_cfg.runtime.title=initCfg.title;
                console.log(`  - Title set to: ${initCfg.title}`);
            }
        }catch(err){
            throw new Error(`  - Error loading or parsing ${fileInit}: ${err.message}`);
        }
    }
    if (fs.existsSync(myCfgPath)) {
        console.log(`  - Found my_cfg.json at ${myCfgPath}, loading configuration...`);        
        // načtení a parse neodchytáváme, pokud existuje musí být vše v pořádku, jinak se musí opravit a nesmí se node spustit
        const myCfg=getJson(myCfgPath);
        try{
            jb_cfg.runtime ??= {};
            jb_cfg.runtime= { ...jb_cfg.runtime, ...myCfg };
            console.log('  - Configuration from my_cfg.json loaded and merged successfully.');
        }catch(err){
            throw new Error(`  - Error loading or parsing my_cfg.json: ${err.message}`);
        }
    }
    console.log('* Configuration loading completed.');
    return jb_cfg;
}

/**
 * Načte další funkce z libs.list pokud existuje v .node-red složce  
 * list obsahuje co řídek to položka a řádek je ve formátu : jméno_modulu=cesta_k_souboru  
 * kde jméno modulu je potom v libs jako property a cesta k souboru buď relativní k '.getPath()' nebo absolutní
 * @param {Object} libs 
 * @returns 
 */
function loadFns(libs) {
    console.log('* Loading additional functions from libs.list if exists...');
    const home = getPath();
    const listFile = path.join(home, 'libs.list');

    let tempLibs = {};          // načteme všechny položky nejdříve sem
    let rootCount = 0;          // počet „root“ modulů

    if (fs.existsSync(listFile)) {
        console.log(`  + Found libs.list at ${listFile}, loading modules...`);
        const lines = fs.readFileSync(listFile, 'utf8').split('\n');
        for (const l of lines) {
            const trimmed = l.trim();
            if (!trimmed || trimmed.startsWith('#')) continue;

            const idx = trimmed.indexOf('=');
            if (idx < 0) {
                console.warn(`  -- Invalid entry in libs.list (no '='): "${trimmed}"`);
                continue;
            }
            let name = trimmed.slice(0, idx).trim();
            let file = trimmed.slice(idx + 1).trim();
            if (!name || !file) {
                console.warn(`  -- Invalid entry in libs.list: "${trimmed}"`);
                continue;
            }

            try {
                console.log(`  ++ Loading module "${name}" from: ${file}`);
                // pokud je to relativní tak přidáme home
                let modulePath = file;
                if (!path.isAbsolute(file)) {
                    modulePath = path.join(home, file);
                }
                const moduleExport = require(modulePath);
                tempLibs[name] = moduleExport;

                // pokud modul má jméno „root“ (např. očekávané) nebo podle tvého pravidla
                if (name === 'root') {
                    rootCount++;
                }
            } catch(err) {
                console.warn(`  -- Could not load module ${name} from ${file}:`, err);
            }
        }
    } else {
        console.log('  - No libs.list found, skipping additional module loading.');
        return libs;
    }

    // Po načtení všech - rozhodnutí zda použít tempLibs nebo prázdné objekty
    if (rootCount === 1) {
        console.log(`  + Exactly one root module found. Using modules as root.`);
        const r=tempLibs['root'];
        delete tempLibs['root'];
        // Začneme s moduly: pokud původní ‚libs‘ měl něco, přepíšeme nebo rozšíříme
        return { ...libs, ...r, ...tempLibs };
    } else {
        if (rootCount === 0) {
            console.warn('  -- No root module found in libs.list. Clearing libs (using {}).');
        } else {
            console.warn('  -- More than one root module found in libs.list. Clearing libs (using {}).');
        }
        return {};  // prázdné libs
    }
}

module.exports = {
    version,
    loadMyCFG,
    getHttps,
    loadMyLoader,
};