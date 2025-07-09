<?php
// phpinfo();
// die('ok');

// ini_set('display_errors', '1');
// ini_set('display_startup_errors', '1');
// error_reporting(E_ALL);

class cfg{
    /**
     * Verze skriptu
     * @var string
     */
    static public string $version = '1.0.0';
    /**
     * Autor skriptu
     * @var string
     */
    static public string $author = 'dvestezar.cz';
    /**
     * Seznam povolených CIDR pro přístup k tomuto skriptu, 
     * pokud zadáme `[]` tak přístup nebude omezen
     * @var string[]
     */
    static public array $allowedCIDR = %cidrs%;
    /**
     * Název souboru s instancemi
     * @var string
     */
    static public function getFilename(){
        // pokud je JSON v tomto adresáři tak necháme
        return __DIR__.'/portInUse.json';
        // pokud je JSON v jiném adresáři tak nastavíme celou cestu k souboru
    }

    /**
     * Název webu, který se zobrazí v hlavičce stránky  
     * Nastavuje Aplikace při kopírování skriptu s JSON souborem
     * @var string
     */
    static public string $siteName = '%site_name%';

    /**
     * Nastavuje tento script z JSON souboru
     * @var string
     */
    static public string $baseUrl = 'Unknown Base URL';

    /**
     * Verze aplikace, která generuje tento skript
     * Nastavuje Aplikace při kopírování skriptu s JSON souborem
     * @var string
     */
    static public string $terminalAppVersion = '%appver%';
    
    /**
     * Datum a čas generování tohoto skriptu - unix timestamp
     * Nastavuje Aplikace při kopírování skriptu s JSON souborem
     * @var int
     */
    static public int $generatedAt = %genAt%;
}

class helper{
    /**
     * Lazy načítání seznamu instancí Node-Red
     * @var string|null
     */
    private static ?string $nod_list=null;


    /**
     * Získá seznam instancí Node-Red z JSON souboru
     * @return string HTML tabulka se seznamem instancí
     * @throws Exception pokud dojde k chybě při načítání nebo zpracování souboru
     */
    static public function get_node_list():string{
        if (self::$nod_list !== null) return self::$nod_list;
        $r=[];
        try{
            $p=cfg::getFilename();
            $x=file_get_contents($p);
            $x=json_decode($x);
            if($x === null) {
                throw new Exception("Chyba při dekódování JSON souboru: " . json_last_error_msg());
            }

            // order instances by port
            usort($x->instances, function($a, $b) {
                return $a[0] <=> $b[0]; // Porovnání podle portu
            });

            cfg::$baseUrl = $x->url ?? 'Unknown Base URL';
    
            $url=$x->url??'';
            
            foreach( ($x->instances??[]) as $k=>$inst){
                list($port, $name, $status) = $inst;

                $class = (strpos($status, "SPUŠTĚNO") !== false)
                    ?
                    "table-success"
                    :
                    "table-danger"
                ;
                $link = (strpos($status, "SPUŠTĚNO") !== false)
                    ?
                    "<a href='$url:$port' target='_blank'>Otevřít</a>"
                    :
                    "- neaktivní-"
                ;
    
                $r[]=<<<HTML
                <tr class='$class'>
                    <td>$name</td>
                    <td>$port</td>
                    <td>$status</td>
                    <td>$link</td>
                </tr>
                HTML;
            }
            if(empty($r)) {
                $r[] = "<tr><td colspan='4'>Žádné instance nenalezeny.</td></tr>";
            }else{
                $r=implode("\n", $r);
                $r=<<<HTML
                <table class="table table-striped table-hover">
                    <thead>
                        <tr class="table-primary">
                            <th>Doména</th>
                            <th>Port</th>
                            <th>Stav</th>
                            <th>Odkaz</th>
                        </tr>
                    </thead>
                    <tbody>
                        $r
                    </tbody>
                </table>
                HTML;
            }
    
        }catch(Exception $e){
            $r='Chyba: '.$e->getMessage();
        }
        if(empty($r)) $r='Žádné instance nenalezeny.';

        self::$nod_list = $r;
        return $r;
    }

    /**
     * Kontrola, zda je IP adresa v rozsahu daného CIDR
     * @param string $ip IP adresa, kterou kontrolujeme
     */
    static function ipInRange($ip, $subnet, $mask) {
        $ip = ip2long($ip);
        $subnet = ip2long($subnet);
        $mask = ~((1 << (32 - $mask)) - 1);
        return ($ip & $mask) === ($subnet & $mask);
    }

    static function checkIP():bool{
        $ip = $_SERVER['REMOTE_ADDR'];
        if(empty(cfg::$allowedCIDR)) return true; // pokud není nastaven žádný CIDR, povolíme přístup
        foreach (cfg::$allowedCIDR as $cidr) {
            $cidr=explode('/', $cidr);
            $subnet = $cidr[0]??null;
            $mask = $cidr[1]??32; // výchozí maska je 32, pokud není zadána
            if ($subnet && self::ipInRange($ip, $subnet, $mask)) {
                return true;
            }
        }
        return false;
    }    
}

$alc_ok = helper::checkIP();
$body = helper::get_node_list();

if(!$alc_ok){
    $body = "<h2>Přístup odepřen</h2><p>Nemáte oprávnění k zobrazení této stránky.</p>";
}

$v=cfg::$version;
$n=cfg::$siteName;
$bsu=cfg::$baseUrl;
$av=cfg::$terminalAppVersion;
$genat = date('Y-m-d H:i:s', cfg::$generatedAt);
echo <<<HTML
<html>
    <head>
        <title>$n - Verze $v</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
<body>
    <div class="container mt-4">
        <h1>Seznam instancí na $bsu</h1>
        <p>
            Autor: <strong>$n</strong><br>
            Verze skriptu: <strong>$v</strong><br>
            Generováno aplikací Node-Red instance ... ver.: <strong>$av</strong><br>
            - generováno: <strong>$genat</strong><br>
        </p>
        $body
    </div>
</body>
</html>
HTML;
