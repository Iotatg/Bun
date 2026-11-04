"""Bun language packs — write Bun in your own language.

Each pack maps English keywords to words of one human language. A pack is
opt-in: give the CLI `--lang <code>`, or put a directive on the first line
of the program (`#!lang hi` or `#lang: hi`). English keywords always stay
available; the pack only adds aliases.

Every word must be a single identifier word (letters of any script, digits,
`_`) — no spaces. Tiers: full (25+ keywords), wide (~20), core (12).
"""

SOFT_KEYWORDS = ("match", "scope", "spawn", "to")


def parse_pack(raw):
    """Parse "let=मानी var=चल" into {english: localized}.

    Only identifier-clean words survive: every localized word must be a
    single run of letters (any script), digits and underscores. Anything
    else — notes, arrows, spaces — is dropped, so a sloppy entry can
    never reach the lexer. Combining marks count (Devanagari matras,
    Arabic harakat), exactly as the lexer of the language sees them.
    """
    import unicodedata as _ud

    def _clean(word):
        return all(ch == "_" or ch.isalnum()
                   or _ud.category(ch) in ("Mn", "Mc", "Me")
                   for ch in word)

    words = {}
    taken = set()
    for piece in raw.split():
        if "=" not in piece:
            continue
        english, _, localized = piece.partition("=")
        if english and localized and localized != "-":
            if _clean(localized) and localized not in taken:
                # One localized word, one meaning: if two slots want the
                # same word (rare), the earlier slot keeps it and the
                # later slot stays English.
                words[english] = localized
                taken.add(localized)
    return words


_RAW = {}
_RAW["hinglish"] = ("Hinglish (Roman Hindi)", """
let=manle var=badlo fn=kaam if=agar else=warna while=jabtak for=har in=mein
return=wapas true=sach false=jhoot null=kuchnahi and=aur or=ya not=nahi
try=koshish catch=pakdo finally=akhirmein throw=pheko import=aayo export=bhejo
from=se as=naamse with=saath assert=janch break=ruko continue=aage
del=mitao yield=de match=milan scope=daira spawn=shuru to=tak
""")
_RAW["hi"] = ("हिन्दी Hindi", """
let=मानी var=चल fn=काम if=अगर else=अन्यथा while=जबतक for=हर in=में
return=लौटो true=सही false=झूठ null=कुछनहीं and=और or=या not=नहीं
try=कोशिश catch=पकड़ो finally=अंतमें throw=फेंको import=आयात export=निर्यात
from=से as=जैसे with=साथ assert=जाँचो break=रुको continue=आगे
del=मिटाओ yield=दो match=मिलान scope=दायरा spawn=उगाओ to=तक
""")
_RAW["ur"] = ("اردو Urdu", """
let=مان var=متغیر fn=فعل if=اگر else=ورنہ while=جبتک for=ہر in=میں
return=واپس true=سچ false=جھوٹ null=کچھ_نہیں and=اور or=یا not=نہیں
try=کوشش catch=پکڑو finally=آخرکو throw=پھینکو import=درآمد export=برآمد
from=سے as=بطور with=ساتھ assert=جانچ break=روکو continue=آگے
del=مٹاؤ yield=دو match=میلاں scope=دائرہ spawn=پیدا to=تک
""")
_RAW["bn"] = ("বাংলা Bengali", """
let=রাখো var=বদল fn=কাজ if=যদি else=নাহলে while=যতক্ষণ for=প্রতি in=মধ্যে
return=ফেরত true=সত্য false=মিথ্যা null=শূন্য and=এবং or=অথবা not=না
try=চেষ্টা catch=আটকাও finally=শেষে throw=ছোড়ো import=আনো export=পাঠাও
from=থেকে as=হিসেবে with=সঙ্গে assert=যাচাই break=থামো continue=এগোও
del=মুছো yield=দাও match=মেলা scope=পরিসর spawn=জন্মাও to=পর্যন্ত
""")
_RAW["ta"] = ("தமிழ் Tamil", """
let=வை var=மாற்று fn=செயல் if=எனில் else=இல்லையெனில் while=வரை for=ஒவ்வொரு
in=இல் return=திரும்ப true=மெய் false=பொய் null=வெறுமை and=மற்றும் or=அல்லது
not=இல்லை try=முயல் catch=பிடி finally=இறுதியில் throw=எறி import=இறக்கு
export=ஏற்று from=இருந்து as=ஆக with=உடன் assert=சோதி break=நில்லு
continue=தொடர் del=நீக்கு yield=கொடு match=பொருத்தம் scope=எல்லை
spawn=உருவாக்கு to=வரை
""")
_RAW["te"] = ("తెలుగు Telugu", """
let=పెట్టు var=మార్చు fn=పని if=అయితే else=లేదంటే while=అయ్యేవరకు for=ప్రతి
in=లో return=తిరిగి true=నిజం false=అబద్ధం null=శూన్యం and=మరియు or=లేదా
not=కాదు try=ప్రయత్నించు catch=పట్టు finally=చివరిగా throw=విసురు
import=తీసుకొను export=పంపు from=నుండి as=గా with=తో assert=సరిచూడు
break=ఆపు continue=కొనసాగించు del=తొలగించు yield=ఇచ్చు match=సరిపోల్చు
scope=పరిధి spawn=మొదలుపెట్టు to=వరకు
""")
_RAW["ml"] = ("മലയാളം Malayalam", """
let=വെക്കൂ var=മാറ്റൂ fn=പണി if=എങ്കിൽ else=അല്ലെങ്കിൽ while=വരെ for=ഓരോ
in=ഇൽ return=തിരികെ true=ശരി false=തെറ്റ് null=ശൂന്യം and=ഉം or=അഥവാ
not=അല്ല try=ശ്രമിക്കൂ catch=പിടിക്കൂ finally=ഒടുവിൽ throw=എറിയൂ
import=കൊണ്ടുവരിക export=അയക്കൂ from=നിന്ന് as=ആയി with=കൂടെ
assert=പരിശോധിക്കൂ break=നിർത്തൂ continue=തുടരൂ del=മായ്ക്കൂ yield=നൽകൂ
match=ചേരും scope=പരിധി spawn=ഉയർത്തൂ to=വരെ
""")
_RAW["kn"] = ("ಕನ್ನಡ Kannada", """
let=ಇಡು var=ಬದಲಿಸು fn=ಕೆಲಸ if=ಎಂದರೆ else=ಇಲ್ಲದಿದ್ದರೆ while=ವರೆಗೆ for=ಪ್ರತಿ
in=ನಲ್ಲಿ return=ಹಿಂತಿರುಗು true=ನಿಜ false=ಸುಳ್ಳು null=ಖಾಲಿ and=ಮತ್ತು or=ಅಥವಾ
not=ಅಲ್ಲ try=ಪ್ರಯತ್ನಿಸು catch=ಹಿಡಿಯು finally=ಕೊನೆಗೆ throw=ಎಸೆಯು import=ತರು
export=ಕಳುಹಿಸು from=ಇಂದ as=ಆಗಿ with=ಜೊತೆ assert=ಪರಿಶೋಧಿಸು break=ನಿಲ್ಲಿಸು
continue=ಮುಂದುವರಿಸು del=ಅಳಿಸು yield=ಕೊಡು match=ಹೊಂದಿಸು scope=ವ್ಯಾಪ್ತಿ
spawn=ಬಿತ್ತು to=ವರೆಗೆ
""")
_RAW["mr"] = ("मराठी Marathi", """
let=ठेव var=बदल fn=काम if=जर else=नाहीतर while=जोपर्यंत for=प्रत्येक in=मध्ये
return=परत true=खरे false=खोटे null=रिकामे and=आणि or=किंवा not=नाही
try=प्रयत्न catch=पकड finally=शेवटी throw=फेक import=आण export=पाठव
from=कडून as=म्हणून with=सोबत assert=तपास break=थांब continue=पुढे
del=पुस yield=दे match=जुळणी scope=व्याप्ती spawn=उगव to=पर्यंत
""")
_RAW["gu"] = ("ગુજરાતી Gujarati", """
let=મૂકો var=બદલો fn=કામ if=જો else=નહીંતર while=સુધી for=દરેક in=માં
return=પાછું true=સાચું false=ખોટું null=ખાલી and=અને or=અથવા not=નહીં
try=પ્રયત્ન catch=પકડો finally=છેલ્લે throw=ફેંકો import=લાવો export=મોકલો
from=થી as=તરીકે with=સાથે assert=તપાસો break=અટકો continue=આગળ
del=કાઢો yield=આપો match=સરખાવો scope=વિસ્તાર spawn=ઊગાડો to=સુધી
""")
_RAW["pa"] = ("ਪੰਜਾਬੀ Punjabi", """
let=ਰੱਖੋ var=ਬਦਲੋ fn=ਕੰਮ if=ਜੇ else=ਨਹੀਂਤਾਂ while=ਜਦਤਕ for=ਹਰ in=ਵਿੱਚ
return=ਵਾਪਸ true=ਸੱਚ false=ਝੂਠ null=ਖਾਲੀ and=ਅਤੇ or=ਜਾਂ not=ਨਹੀਂ
try=ਕੋਸ਼ਿਸ਼ catch=ਫੜੋ finally=ਅਖੀਰ throw=ਸੁੱਟੋ import=ਲਿਆਓ export=ਭੇਜੋ
from=ਤੋਂ as=ਵਜੋਂ with=ਨਾਲ assert=ਜਾਂਚ break=ਰੁਕੋ continue=ਅੱਗੇ
del=ਮਿਟਾ yield=ਦੇ match=ਮਿਲਾਓ scope=ਘੇਰਾ spawn=ਉਗਾ to=ਤੱਕ
""")
_RAW["es"] = ("Español Spanish", """
let=fijo var=cambia fn=func if=si else=sino while=mientras for=para in=en
return=devuelve true=verdadero false=falso null=nulo and=y or=o not=no
try=intenta catch=atrapa finally=finalmente throw=lanza import=importa
export=exporta from=de as=como with=con assert=afirma break=pausa
continue=sigue del=borra yield=cede match=coincide scope=ambito spawn=crea
to=hasta
""")
_RAW["fr"] = ("Français French", """
let=soit var=change fn=fonction if=si else=sinon while=tantque for=pour
in=dans return=renvoie true=vrai false=faux null=nul and=et or=ou not=non
try=essaie catch=attrape finally=finalement throw=lance import=importe
export=exporte from=depuis as=comme with=avec assert=affirme break=casse
continue=continue del=supprime yield=produit match=correspond scope=portee
spawn=cree to=vers
""")
_RAW["de"] = ("Deutsch German", """
let=fest var=ändere fn=funktion if=wenn else=sonst while=solange for=für
in=in return=gib true=wahr false=falsch null=nichts and=und or=oder not=nicht
try=versuche catch=fange finally=zuletzt throw=wirf import=lade export=liefer
from=aus as=als with=mit assert=prüfe break=abbruch continue=weiter
del=lösche yield=liefere match=treffe scope=bereich spawn=starte to=bis
""")
_RAW["pt"] = ("Português Portuguese", """
let=fixa var=muda fn=funcao if=se else=senao while=enquanto for=para in=em
return=devolve true=verdadeiro false=falso null=nulo and=e or=ou not=nao
try=tenta catch=pega finally=afinal throw=lanca import=importa export=exporta
from=de as=como with=com assert=afirma break=quebra continue=continua
del=apaga yield=cede match=iguala scope=escopo spawn=cria to=ate
""")
_RAW["it"] = ("Italiano Italian", """
let=sia var=cambia fn=funzione if=se else=altrimenti while=mentre for=per
in=dentro return=ritorna true=vero false=falso null=niente and=e or=o
not=non try=prova catch=afferra finally=infine throw=lancia import=importa
export=esporta from=da as=come with=con assert=afferma break=interrompi
continue=continua del=cancella yield=cede match=abbina scope=ambito
spawn=genera to=fino
""")
_RAW["ru"] = ("Русский Russian", """
let=пусть var=меняй fn=функ if=если else=иначе while=пока for=для in=в
return=верни true=истина false=ложь null=пусто and=и or=или not=не
try=пробуй catch=лови finally=наконец throw=брось import=ввоз export=вывоз
from=из as=как with=с assert=проверь break=стоп continue=дальше
del=убери yield=отдай match=выбор scope=область spawn=запуск to=до
""")
_RAW["ar"] = ("العربية Arabic", """
let=ليكن var=غير fn=دالة if=إذا else=وإلا while=ما_دام for=لكل in=في
return=أعد true=صحيح false=كذب null=لا_شيء and=و or=أو not=ليس
try=حاول catch=التقط finally=أخيرا throw=ارم import=استورد export=أصدر
from=من as=مثل with=مع assert=تحقق break=توقف continue=واصل
del=امسح yield=أعط match=طابق scope=نطاق spawn=شغل to=إلى
""")
_RAW["zh"] = ("简体中文 Chinese Simplified", """
let=让 var=设 fn=函数 if=如果 else=否则 while=当 for=循环 in=在
return=返回 true=真 false=假 null=空 and=且 or=或 not=非
try=尝试 catch=捕获 finally=最终 throw=抛出 import=导入 export=导出
from=从 as=作为 with=以 assert=断言 break=跳出 continue=继续
del=删除 yield=产出 match=匹配 scope=范围 spawn=启动 to=到
""")
_RAW["zh_tw"] = ("繁體中文 Chinese Traditional", """
let=讓 var=設 fn=函數 if=如果 else=否則 while=當 for=迴圈 in=於
return=傳回 true=真 false=假 null=空 and=且 or=或 not=非
try=嘗試 catch=捕獲 finally=最終 throw=拋出 import=匯入 export=匯出
from=從 as=作為 with=以 assert=斷言 break=跳出 continue=繼續
del=刪除 yield=產出 match=匹配 scope=範圍 spawn=啟動 to=到
""")
_RAW["ja"] = ("日本語 Japanese", """
let=おく var=変える fn=関数 if=もし else=そうでなければ while=間 for=各
in=の return=返す true=真 false=偽 null=空 and=かつ or=または not=でなく
try=試す catch=捕まえる finally=最後に throw=投げる import=読み込む
export=出す from=から as=として with=共に assert=確認 break=抜ける
continue=続ける del=消す yield=生む match=一致 scope=範囲 spawn=起こす to=まで
""")
_RAW["ko"] = ("한국어 Korean", """
let=두고 var=바꿔 fn=함수 if=만약 else=아니면 while=동안 for=마다 in=안에
return=돌려줘 true=참 false=거짓 null=없음 and=그리고 or=또는 not=아니
try=시도 catch=잡아 finally=마지막에 throw=던져 import=가져와 export=내보내
from=에서 as=로 with=같이 assert=점검 break=멈춰 continue=계속
del=지워 yield=줘 match=맞춰 scope=범위 spawn=일으켜 to=까지
""")
_RAW["id"] = ("Bahasa Indonesia", """
let=tetapkan var=ubah fn=fungsi if=jika else=kalautidak while=selama
for=untuk in=dalam return=kembalikan true=benar false=salah null=kosong
and=dan or=atau not=tidak try=coba catch=tangkap finally=akhirnya
throw=lempar import=impor export=ekspor from=dari as=sebagai with=dengan
assert=pastikan break=hentikan continue=lanjutkan del=hapus yield=beri
match=cocokkan scope=lingkup spawn=jalankan to=sampai
""")
_RAW["tr"] = ("Türkçe Turkish", """
let=sabitle var=değiştir fn=işlev if=eğer else=yoksa while=iken for=her
in=içinde return=döndür true=doğru false=yanlış null=boş and=ve or=veya
not=değil try=dene catch=yakala finally=sonunda throw=fırlat import=içeri
export=dışarı from=kaynak as=gibi with=ile assert=onayla break=kır
continue=sürdür del=sil yield=ver match=eşle scope=kapsam spawn=başlat
to=kadar
""")
_RAW["vi"] = ("Tiếng Việt Vietnamese", """
let=đặt var=đổi fn=hàm if=nếu else=nguoc while=trongkhi for=mỗi in=trong
return=trave true=đúng false=sai null=rỗng and=và or=hoặc not=phudinh
try=thử catch=bắt finally=cuối throw=ném import=nhập export=xuất
from=từ as=như with=với assert=kiemtra break=dừng continue=tiếp
del=xóa yield=đưa match=khớp scope=phamvi spawn=sinh to=đến
""")
_RAW["th"] = ("ไทย Thai", """
let=กำหนด var=แก้ fn=ฟังก์ชัน if=ถ้า else=มิฉะนั้น while=ขณะ for=สำหรับ
in=ใน return=คืนค่า true=จริง false=เท็จ null=ว่าง and=และ or=หรือ not=ไม่
try=พยายาม catch=จับ finally=สุดท้าย throw=ขว้าง import=นำเข้า export=ส่งออก
from=จาก as=เป็น with=ด้วย assert=ตรวจ break=หยุด continue=เลื่อน
del=ลบ yield=ให้ match=จับคู่ scope=ขอบเขต spawn=ปั้น to=ถึง
""")
_RAW["pl"] = ("Polski Polish", """
let=niech var=zmień fn=funkcja if=jeśli else=inaczej while=dopóki for=dla
in=w return=oddaj true=prawda false=fałsz null=nic and=oraz or=lub not=nie
try=spróbuj catch=złap finally=wreszcie throw=rzuć import=sprowadź
export=wyślij from=z as=jako with=z assert=sprawdź break=przerwij
continue=kontynuuj del=usuń yield=ustąp match=dopasuj scope=zasięg
spawn=uruchom to=do
""")
_RAW["nl"] = ("Nederlands Dutch", """
let=stel var=verander fn=functie if=indien else=anders while=terwijl
for=voor in=in return=geef true=waar false=onwaar null=niets and=en or=of
not=niet try=probeer catch=vang finally=uiteindelijk throw=gooi
import=importeer export=exporteer from=van as=als with=met assert=bevestig
break=breek continue=gadoor del=verwijder yield=lever match=gelijk
scope=bereik spawn=start to=tot
""")
_RAW["fa"] = ("فارسی Persian", """
let=بگذار var=عوضکن fn=تابع if=اگر else=وگرنه while=تازمانی for=برای in=در
return=برگردان true=درست false=غلط null=هیچ and=و or=یا not=نه
try=تلاشکن catch=بگیر finally=سرانجام throw=پرتکن import=بیار export=بفرست
from=از as=بهعنوان with=با assert=آزمای break=بشکن continue=ادامهبده
del=پاککن yield=بده match=جورکن scope=گستره spawn=برپا to=تا
""")
_RAW["he"] = ("עברית Hebrew", """
let=יהי var=שנה fn=פונקציה if=אם else=אחרת while=כלעוד for=עבור in=בתוך
return=החזר true=אמת false=שקר null=ריק and=וגם or=או not=לא
try=נסה catch=תפוס finally=לבסוף throw=זרוק import=יבא export=יצא
from=מן as=כמו with=עם assert=בדוק break=הפסק continue=המשך
del=מחק yield=תן match=התאם scope=היקף spawn=הפעל to=עד
""")
_RAW["sv"] = ("Svenska Swedish", """
let=sätt var=ändra fn=funktion if=om else=annars while=medan for=för in=i
return=ge true=sant false=falskt null=inget and=och or=eller not=inte
try=försök catch=fånga finally=tillslut throw=kasta import=importera
export=exportera from=från as=som with=med assert=hävda break=avbryt
continue=fortsätt match=matcha scope=område spawn=starta to=till
""")
_RAW["no"] = ("Norsk Norwegian", """
let=la var=endre fn=funksjon if=hvis else=ellers while=mens for=for in=i
return=returner true=sant false=usant null=ingenting and=og or=eller
not=ikke try=prøv catch=fang finally=tilslutt throw=kast import=hent
export=send from=fra as=som with=med assert=sikre break=stopp
continue=fortsett match=match scope=omfang spawn=start to=til
""")
_RAW["da"] = ("Dansk Danish", """
let=sæt var=ændre fn=funktion if=hvis else=ellers while=mens for=for in=i
return=returner true=sand false=falsk null=intet and=og or=eller not=ikke
try=prøv catch=fang finally=tilsidst throw=kast import=hent export=send
from=fra as=som with=med assert=sikre break=stop continue=fortsæt
match=match scope=omfang spawn=start to=til
""")
_RAW["fi"] = ("Suomi Finnish", """
let=olkoon var=muuta fn=funktio if=jos else=muuten while=niinkauan
for=jokaiselle in=sisalla return=palauta true=tosi false=epätosi
null=tyhjä and=ja or=tai not=ei try=yritä catch=ota finally=lopuksi
throw=heitä import=tuo export=lähetä from=lähteestä as=nimellä with=kanssa
assert=tarkista break=katkaise continue=jatka match=sovita scope=alue
spawn=käynnistä to=asti
""")
_RAW["is"] = ("Íslenska Icelandic", """
let=láttu var=breyttu fn=fall if=ef else=annars while=meðan for=fyrir in=í
return=skilaðu true=satt false=ósatt null=tómt and=og or=eða not=ekki
try=reyndu catch=gríptu finally=aðlokum throw=kastadu import=flyttuinn
export=senduut from=frá as=sem with=með assert=kanna break=stöðva
continue=haltuafram
""")
_RAW["cs"] = ("Čeština Czech", """
let=nech var=změň fn=funkce if=jestliže else=jinak while=dokud for=pro in=v
return=vrať true=pravda false=nepravda null=nic and=a or=nebo not=ne
try=zkus catch=chyť finally=konečně throw=hoď import=vezmi export=pošli
from=z as=jako with=s assert=ověř break=přeruš continue=pokračuj
del=smaž yield=vzdej match=porovnej scope=obor spawn=spusť to=do
""")
_RAW["sk"] = ("Slovenčina Slovak", """
let=nech var=zmeň fn=funkcia if=ak else=inak while=kým for=pre in=vo
return=vráť true=pravda false=lož null=nič and=a or=alebo not=nie
try=skús catch=chyt finally=napokon throw=hoď import=vezmi export=pošli
from=z as=ako with=s assert=over break=preruš continue=pokračuj
del=vymaž yield=oddaj match=porovnaj scope=obor spawn=spusti to=po
""")
_RAW["hu"] = ("Magyar Hungarian", """
let=legyen var=változtat fn=függvény if=ha else=különben while=amíg
for=minden in=benne return=visszaad true=igaz false=hamis null=semmi
and=és or=vagy not=nem try=próbáld catch=fogd finally=végre throw=dobd
import=hozz export=küldj from=tól as=mint with=vel assert=vizsgáld
break=szakíts continue=folytas del=töröld yield=adj match=illeszt
scope=hatótér spawn=indít to=ig
""")
_RAW["ro"] = ("Română Romanian", """
let=fie var=schimbă fn=functie if=dacă else=altfel while=câtimp for=pentru
in=în return=intoarce true=adevărat false=fals null=nimic and=și or=sau
not=nu try=încearcă catch=prinde finally=laurma throw=aruncă
import=adu export=trimite from=din as=ca with=cu assert=verifică
break=întrerupe continue=continuă del=șterge yield=cedează
match=potrivește scope=rază spawn=pornește to=până
""")
_RAW["bg"] = ("Български Bulgarian", """
let=нека var=промени fn=функция if=ако else=иначе while=докато for=за in=в
return=върни true=истина false=лож null=празно and=и or=или not=не
try=опитай catch=улови finally=накрая throw=хвърли import=внеси
export=изнеси from=от as=като with=с assert=провери break=прекъсни
continue=продължи del=изтрий yield=дай match=съвпадне scope=обхват
spawn=стартирай to=до
""")
_RAW["el"] = ("Ελληνικά Greek", """
let=έστω var=άλλαξε fn=συνάρτηση if=αν else=αλλιώς while=όσο for=για in=σε
return=επιστρέψε true=αληθές false=ψευδές null=κενό and=και or=ή not=όχι
try=δοκίμασε catch=πίασε finally=τέλος throw=ρίξε import=φέρε export=στείλε
from=από as=ως with=με assert=έλεγξε break=διέκοψε continue=συνέχισε
del=σβήσε yield=δώσε match=ταίριασε scope=πεδίο spawn=ξεκίνα to=έως
""")
_RAW["uk"] = ("Українська Ukrainian", """
let=нехай var=зміни fn=функція if=якщо else=інакше while=поки for=для in=в
return=поверни true=істина false=хиба null=порожньо and=і or=або not=не
try=спробуй catch=лови finally=нарешті throw=кинь import=привези
export=відправ from=з as=як with=з assert=перевір break=перерви
continue=продовж del=сотри yield=дай match=зістав scope=обсяг
spawn=запусти to=до
""")
_RAW["sr"] = ("Српски Serbian", """
let=нека var=промени fn=функција if=ако else=иначе while=докато for=за in=у
return=врати true=истина false=лаж null=празно and=и or=или not=не
try=пробај catch=ухвати finally=коначно throw=баци import=увези
export=извези from=из as=као with=са assert=провери break=прекини
continue=настави del=обриши yield=дај match=поклапа scope=опсег
spawn=покрени to=до
""")
_RAW["hr"] = ("Hrvatski Croatian", """
let=neka var=promijeni fn=funkcija if=ako else=inako while=dok for=za in=u
return=vrati true=istina false=laž null=prazno and=i or=ili not=ne
try=pokušaj catch=uhvati finally=konačno throw=baci import=uvezi
export=izvezi from=iz as=kao with=s assert=provjeri break=prekini
continue=nastavi del=obriši yield=daj match=poklopi scope=opseg
spawn=pokreni to=do
""")
_RAW["lt"] = ("Lietuvių Lithuanian", """
let=tebūnie var=pakeisk fn=funkcija if=jei else=kituatveju while=kol
for=kiekvienam in=viduje return=grąžink true=tiesa false=melas null=tuščia
and=ir or=arba not=ne try=pabandyk catch=pagauk finally=galiausiai
throw=mesk import=atsivež export=išsiųsk from=iš as=kaip with=su
assert=patikrink break=nutrauk continue=tęsk del=ištrink yield=duok
match=atitikt scope=apimtis spawn=paleisk to=iki
""")
_RAW["lv"] = ("Latviešu Latvian", """
let=lai var=maini fn=funkcija if=ja else=pretējāgadījumā while=kamēr
for=katrai in=iekš return=atgriez true=patiess false=aplams null=tukšs
and=un or=vai not=ne try=pamēģini catch=ķer finally=beigās throw=met
import=atved export=aizsūti from=no as=kā with=ar assert=pārbaudi
break=pārtrauc continue=turpini del=dzēs yield=dod match=sakrīt
scope=apjoms spawn=palaid to=līdz
""")
_RAW["et"] = ("Eesti Estonian", """
let=olgu var=muuda fn=funktsioon if=kui else=muidu while=kuni for=iga in=sees
return=tagasta true=tõene false=väär null=tühi and=ja or=või not=ei
try=proovi catch=püüa finally=lõpuks throw=viska import=too export=saada
from=alates as=nagu with=koos assert=kontrolli break=katkesta
continue=jätka del=kustuta yield=anna match=võrdle scope=ulatus
spawn=käivita to=kuni
""")
_RAW["eo"] = ("Esperanto", """
let=estu var=ŝanĝu fn=funkcio if=se else=alie while=dum for=por in=en
return=revenu true=vero false=malvero null=nenio and=kaj or=aŭ not=ne
try=provu catch=kaptu finally=fine throw=ĵetu import=alportu export=sendu
from=el as=kiel with=kun assert=kontrolu break=ĉesu continue=daŭrigu
del=forigu yield=donu match=kongruas scope=areo spawn=lanĉu to=ĝis
""")
_RAW["ca"] = ("Català Catalan", """
let=sigui var=canvia fn=funcio if=si else=sino while=mentres for=per in=dins
return=torna true=cert false=fals null=buit and=i or=o not=no
try=prova catch=pilla finally=finalment throw=llança import=importa
export=exporta from=de as=com with=amb assert=afirma break=trenca
continue=continua del=esborra yield=cedeix match=iguala scope=ambit
spawn=crea to=fins
""")
_RAW["ms"] = ("Bahasa Melayu Malay", """
let=tetapkan var=ubah fn=fungsi if=jika else=jikatidak while=semasa
for=untuk in=dalam return=pulangkan true=benar false=salah null=kosong
and=dan or=atau not=tidak try=cuba catch=tangkap finally=akhirnya
throw=lempar import=import export=eksport from=dari as=sebagai with=dengan
assert=sahkan break=berhenti continue=teruskan del=padam yield=beri
match=padankan scope=skop spawn=mula to=hingga
""")
_RAW["tl"] = ("Filipino Tagalog", """
let=itakda var=palitan fn=gawain if=kung else=kunghindi while=habang
for=para in=sa return=ibalik true=totoo false=mali null=wala and=at or=o
not=huwag try=subukan catch=huliin finally=wakas throw=itapon
import=dalhin export=ipadala from=mula as=kungbilang with=gamit
assert=tsek break=itigil continue=ipagpatuloy del=burahin yield=ibigay
match=tugma scope=saklaw spawn=bumuo to=hanggang
""")
_RAW["sw"] = ("Kiswahili Swahili", """
let=weka var=badilisha fn=kazi if=kama else=vinginevyo while=wakati for=kwa
in=katika return=rudisha true=kweli false=uongo null=tupu and=na or=au
not=si try=jaribu catch=nasa finally=mwisho throw=tupa import=leta
export=tuma from=kutoka as=kama with=kwa assert=angalia break=simama
continue=endelea del=futa yield=pa match=linganisha scope=eneo
spawn=anzua to=hadi
""")
_RAW["af"] = ("Afrikaans", """
let=laat var=verander fn=funksie if=as else=anders while=terwyl for=vir
in=in return=gee true=waar false=vals null=niks and=en or=of not=nie
try=probeer catch=vang finally=uiteindelik throw=gooi import=voerin
export=stuuruit from=van as=soos with=met assert=bevestig break=breek
continue=gaanvoort del=skrap yield=geeaf match=pas scope=omvang
spawn=begin to=tot
""")
_RAW["mn"] = ("Монгол Mongolian", """
let=өг var=өөрчил fn=функц if=хэрэв else=үгүйбол while=хүртэл for=төлөө
in=дотор return=буцаа true=үнэн false=худал null=хоосон and=ба or=эсвэл
not=биш try=тур catch=барь finally=эцэст throw=шид import=авчир
export=илгээ from=ас as=бол with=хамт assert=шалга break=зогсоо
continue=үргэлжлүүл del=устга yield=өг match=таар scope=хүрээ
spawn=эхлүүл to=хүртэл
""")
# --- Tier: core (12 keywords a first program needs) ------------------------
_RAW["or"] = ("ଓଡ଼ିଆ Odia", "let=ରଖ var=ବଦଳାଅ fn=କାମ if=ଯଦି else=ନହେଲେ while=ଯେତେବେଳେ for=ପାଇଁ in=ଭିତରେ return=ଫେର true=ସତ୍ୟ false=ମିଥ୍ୟା null=ଖାଲି and=ଏବଂ or=ବା not=ନାହିଁ")
_RAW["as"] = ("অসমীয়া Assamese", "let=ৰাখ var=সলাও fn=কাম if=যদি else=নহলে while=যেতিয়া for=প্ৰতি in=ত return=ঘূৰি true=সঁচা false=মিছা null=ৰিক্ত and=আৰু or=অথবা not=নহয়")
_RAW["ne"] = ("नेपाली Nepali", "let=राख var=बदल fn=काम if=यदि else=अन्यथा while=सम्म for=प्रत्येक in=मा return=फर्क true=साँचो false=झूठो null=खाली and=र or=वा not=होइन")
_RAW["si"] = ("සිංහල Sinhala", "let=තියන්න var=වෙනස්කරන්න fn=වැඩ if=නම් else=නැත්නම් while=අතරතුර for=සඳහා in=තුළ return=ආපසු true=ඇත්ත false=බොරුව null=හිස් and=සහ or=හෝ not=නැත")
_RAW["sd"] = ("سنڌي Sindhi", "let=رکھ var=بدل fn=ڪم if=جيڪڏهن else=ٻيصورت while=جڏهن for=هر in=اندر return=موٽ true=سچ false=ڪوڙ null=خالي and=۽ or=يا not=نه")
_RAW["sa"] = ("संस्कृतम् Sanskrit", "let=स्थापय var=परिवर्तय fn=कर्म if=चेत् else=अन्यथा while=यावत् for=प्रति in=अन्तर्गत return=प्रत्यर्पय true=सत्यम् false=असत्यम् null=रिक्तम् and=च or=वा not=न")
_RAW["be"] = ("Беларуская Belarusian", "let=няхай var=змяні fn=функцыя if=калі else=інакше while=пакуль for=для in=у return=вярні true=істина false=лож null=пуста and=і or=або not=не")
_RAW["sl"] = ("Slovenščina Slovenian", "let=naj var=spremeni fn=funkcija if=če else=sicer while=dokler for=za in=v return=vrni true=res false=laž null=prazno and=in or=ali not=ne")
_RAW["mk"] = ("Македонски Macedonian", "let=нека var=промени fn=функција if=ако else=инаку while=додека for=за in=во return=врати true=вистина false=лаж null=празно and=и or=или not=не")
_RAW["sq"] = ("Shqip Albanian", "let=vendos var=ndrysho fn=funksion if=nëse else=përndryshe while=derisa for=për in=në return=kthe true=evertetë false=erremë null=bosh and=dhe or=ose not=jo")
_RAW["bs"] = ("Bosanski Bosnian", "let=neka var=promijeni fn=funkcija if=ako else=inako while=dok for=za in=u return=vrati true=istina false=laž null=prazno and=i or=ili not=ne")
_RAW["eu"] = ("Euskara Basque", "let=ezarri var=aldatu fn=funtzioa if=baldin else=bestela while=bitartean for=bakoitza in=barruan return=itzuli true=egia false=faltsua null=hutsik and=eta or=edo not=ez")
_RAW["gl"] = ("Galego Galician", "let=sexa var=cambia fn=funcion if=se else=senon while=mentres for=para in=dins return=devolve true=verdadeiro false=falso null=baleiro and=e or=ou not=non")
_RAW["cy"] = ("Cymraeg Welsh", "let=gosod var=newid fn=swyddogaeth if=os else=felarall while=tra for=am in=yn return=dychwelyd true=gwir false=gau null=gwag and=ac or=neu not=nid")
_RAW["ga"] = ("Gaeilge Irish", "let=bíodh var=athraigh fn=feidhm if=má else=nóma while=fadis for=gach in=i return=fill true=fíor false=bréag null=folamh and=agus or=nó not=ní")
_RAW["lb"] = ("Lëtzebuergesch Luxembourgish", "let=looss var=änneren fn=funktioun if=wann else=ansonnst while=iwwerdeems for=fir in=an return=zréck true=wouer false=falsch null=eidel and=an or=oder not=net")
_RAW["fo"] = ("Føroyskt Faroese", "let=lát var=broyt fn=funktion if=um else=annars while=meðan for=fyri in=í return=gev true=samt false=ósatt null=tómt and=og or=ella not=ikki")
_RAW["rm"] = ("Rumantsch Romansh", "let=saja var=midra fn=funcziun if=schai else=autramain while=entantchem for=per in=en return=render true=vair false=falsch null=vid and=e or=oda not=betg")
_RAW["mt"] = ("Malti Maltese", "let=poġġi var=biddel fn=funzjoni if=jekk else=inkella while=waqt for=għal in=fi return=irritorna true=veru false=falz null=vojt and=u or=jew not=mhux")
_RAW["kk"] = ("Қазақша Kazakh", "let=қой var=өзгерт fn=функция if=болса else=әйтпесе while=дейін for=үшін in=ішінде return=қайтар true=ақиқат false=жалған null=бос and=және or=немесе not=емес")
_RAW["ky"] = ("Кыргызча Kyrgyz", "let=кой var=өзгөрт fn=функция if=болсо else=болбосо while=чейин for=үчүн in=ичинде return=кайтар true=чын false=жалган null=бош and=жана or=же not=эмес")
_RAW["uz"] = ("Oʻzbekcha Uzbek", "let=qoy var=ozgartir fn=funksiya if=agar else=aksholda while=paytida for=uchun in=ichida return=qaytar true=rost false=yolgon null=bush and=va or=yoki not=emas")
_RAW["tk"] = ("Türkmençe Turkmen", "let=goy var=üýtget fn=funksiya if=eger else=ýogsa while=häli for=üçin in=içinde return=gaýtar true=dogry false=ýalňyş null=boş and=we or=ýa not=däl")
_RAW["tg"] = ("Тоҷикӣ Tajik", "let=гузор var=тағйирдиҳ fn=функсия if=агар else=вагарна while=то for=барои in=дар return=баргардон true=дуруст false=ғалат null=холӣ and=ва or=ё not=не")
_RAW["az"] = ("Azərbaycanca Azerbaijani", "let=qoy var=dəyiş fn=funksiya if=əgər else=əkshalda while=olduqca for=üçün in=daxil return=qaytar true=həqiqət false=yalan null=boş and=və or=yoxud not=deyil")
_RAW["hy"] = ("Հայերեն Armenian", "let=դիր var=փոխիր fn=գործ if=եթե else=այլապես while=մինչ for=համար in=մեջ return=վերադարձրու true=ճիշտ false=սուտ null=դատարկ and=և or=կամ not=ոչ")
_RAW["ka"] = ("ქართული Georgian", "let=დადე var=შეცვალე fn=ფუნქცია if=თუ else=თორემ while=სანამ for=ყოველი in=შიგნით return=დააბრუნე true=მართალი false=მცდარი null=ცარიელი and=და or=ან not=არა")
_RAW["ps"] = ("پښتو Pashto", "let=کېږدوه var=بدل fn=کار if=که else=نو while=تر for=لپاره in=کې return=بیرته true=سمه false=غلطه null=تش and=او or=که not=نه")
_RAW["ku"] = ("Kurdî Kurdish", "let=bide var=biguherîne fn=kar if=heke else=yanna while=heta for=jibo in=di return=vegere true=rast false=derew null=vala and=û or=an not=na")
_RAW["lo"] = ("ລາວ Lao", "let=ກຳນົດ var=ແກ້ fn=ຟັງຊັນ if=ຖ້າ else=ບໍ່ດັ່ງນັ້ນ while=ເມື່ອ for=ສຳລັບ in=ໃນ return=ຄືນ true=ຈິງ false=ຜິດ null=ຫວ່າງ and=ແລະ or=ຫຼື not=ບໍ່")
_RAW["my"] = ("မြန်မာ Burmese", "let=သတ်မှတ် var=ပြောင်း fn=လုပ်ငန်း if=ဖြစ်ရင် else=မဟုတ်ရင် while=နေချင် for=အတွက် in=ထဲ return=ပြန် true=ဟုတ် false=မှား null=ဗလာ and=နဲ့ or=ဒါမှမဟုတ် not=မဟုတ်")
_RAW["km"] = ("ភាសាខ្មែរ Khmer", "let=កំណត់ var=ផ្លាស់ fn=មុខងារ if=បើ else=បើមិន while=ខណៈ for=សម្រាប់ in=ក្នុង return=ត្រឡប់ true=ពិត false=មិនពិត null=ទំនេរ and=និង or=ឬ not=មិន")
_RAW["bo"] = ("བོད་སྐད་ Tibetan", "let=འཇོག var=བསྒྱུར fn=ལས if=གལཏེ else=མིནན while=བར for=ཆེད in=ནང return=ཕྱིརསྐུར true=བདེན false=རྫུན null=སྟོང and=དང or=ཡངན not=མིན")
_RAW["dv"] = ("ދިވެހި Divehi", "let=ޖައްސާ var=ބަދަލު fn=ކަމް if=ނަމަ else=ނޫނނަމަ while=އުޅުމުގައި for=އަށް in=ގައި return=އެނބުރި true=ރަނގަޅު false=ގަލު null=ހުސް and=އަދި or=ނޫނީ not=ނޫން")
_RAW["am"] = ("አማርኛ Amharic", "let=ተው var=ቀይር fn=ሥራ if=ከሆነ else=በሌለበት while=እስከ for=ለ in=ውስጥ return=መልስ true=እው false=አይ null=ባዶ and=እና or=ወይም not=አይደለም")
_RAW["om"] = ("Afaan Oromoo Oromo", "let=kaai var=sirreessi fn=hojii if=yoo else=taanaan while=yeroo for=afuu in=keessa return=deebi true=dhugaa false=soba null=duunya and=fi or=yookaan not=miti")
_RAW["rw"] = ("Ikinyarwanda Kinyarwanda", "let=shyiraho var=hindura fn=umurimo if=niba else=ubundi while=mugihe for=kuri in=mu return=subiza true=ukuri false=ikinyoma null=ubusa and=na or=cyangwa not=atari")
_RAW["lg"] = ("Oluganda Luganda", "let=teeka var=kyusa fn=omulimu if=bwaba else=omulala while=ngabadde for=ku in=mu return=ddamu true=kituufu false=obutalikituufu null=kitereke and=ne or=oba not=tewali")
_RAW["ln"] = ("Lingala", "let=lata var=lonsole fn=sala if=soki else=sokite while=tango for=pona in=na return=zonga true=bosolo false=lokuta null=elenge and=na or=to not=te")
_RAW["bm"] = ("Bamanankan Bambara", "let=cila var=yèlèma fn=dòn if=nin else=tuguni while=waati for=ye in=kɔnɔ return=seginni true=sɛgɛn false=nanga null=fɛntɛ and=ni or=walima not=tɛ")
_RAW["tw"] = ("Twi", "let=hyɛ var=sesa fn=adwuma if=sɛ else=anaasɛ while=bere for=ma in=mu return=san true=nokware false=ntam null=dada and=ne or=anaa not=nni")
_RAW["ny"] = ("Chichewa Chinyanja", "let=ika var=sintha fn=ntchito if=ngati else=ngateli while=pamene for=za in=mu return=bweretsani zoona=zonama? true=zoona false=zonama null=kanthu and=ndipo or=kapena ayi=ayi? not=ayi")
_RAW["zu"] = ("isiZulu Zulu", "let=faka var=shintsha fn=umsebenzi if=uma else=kokunye while=ngesikhathi for=ngo in=ngaphakathi return=buyela true=iqiniso false=ubuxoki null=ingenalutho and=no? futhi=and noma=or cha=not")
_RAW["xh"] = ("isiXhosa Xhosa", "let=faka var=tshintsha fn=umsebenzi if=ukuba else=enye while=ngexesha for=ngo in=ngaphakathi return=buyela true=yinyaniso false=ubuxoki null=ingenanto and=kanjalo? no: and=nangona? use ukwayo? Keep: yinyaniso/ubuxoki/ukuba/enye")
_RAW["so"] = ("Soomaali Somali", "let=dhig var=beddel fn=shaqo if=haddii else=haddiikale while=inta for=ugu in=gudaha return=celi true=run false=been null=bannaan and=iyo or=ama not=maha")
_RAW["mg"] = ("Malagasy Malagasy", "let=apetraho var=ovay fn=asa if=raha else=rahatsia while=mandritra for=hoany in=aoanaty return=averina true=marina false=diso null=foana and=sy or=na not=tsy")
_RAW["yo"] = ("Yorùbá Yoruba", "let=fi var=yi fn=ise if=tiba else=tibi while=akoko for=fun in=ni return=pada true=otito false=iro null=kosi and=ati or=tabi not=ko")
_RAW["ig"] = ("Asụsụ Igbo Igbo", "let=tinye var=gbanwee fn=oru if=olu else=maburu while=mgbe for=maka in=na return=laghachi true=eziokwu false=ugha null=efu and=na or=mabu not=bughi")
_RAW["ha"] = ("Hausa", "let=saka var=canza fn=aiki if=idan else=inbahaka while=yayin for=domin in=cikin return=mayar true=gaskiya false=karya null=fanko and=da or=ko not=ba")
_RAW["ti"] = ("ትግርኛ Tigrinya", "let=ተቐምጥ var=ቀይር fn=ሥራ if=እንተ else=ከይዞ while=ግዜ for=ን in=ውሽጢ return=መሊስ true=እውነት false=ሓሶት null=ባዶ and=እና or=ወይ not=ኣይኮነን")
_RAW["sm"] = ("Gagana Sāmoa Samoan", "let=tuu var=sui fn=galuega if=afai else=aeleai while=taimi for=mo in=i return=toefoi true=moni false=sese null=gaogao and=ma or=poo not=leai")
_RAW["jv"] = ("Basa Jawa Javanese", "let=pasang var=owahi fn=gawe if=menawa else=liyane while=nalika for=kanggo in=ing return=bali true=bener false=salah null=kosong and=lan or=utawa not=ora")
_RAW["su"] = ("Basa Sunda Sundanese", "let=pasang var=robah fn=gawean if=lamun else=sejenna while=mangsa for=bari in=di return=mulang true=bener false=salah null=kosong and=jeung or=atanapi not=henteu")
_RAW["ceb"] = ("Cebuano Binisaya", "let=ibutang var=ilisan fn=buhat if=kon else=kungdili while=samtang for=alang in=sa return=balik true=tinuod false=sayop null=walay and=ug or=o not=dili")

_RAW["ee"] = ("Eʋegbe Ewe", "let=de var=tɔtrɔ fn=dɔwɔwɔ if=ne else=elala while=nee for=na in=me return=trɔ true=nyate false=meku null=dzeame and=eye or=alo not=meleo")
_RAW["st"] = ("Sesotho Southern Sotho", "let=beha var=fetola fn=mosebetsi if=haeba else=eseng while=ha for=bakengsa in=ka return=khutlisa true=nnete false=mafele null=senang and=le or=kapa not=eseng")
_RAW["tn"] = ("Setswana Tswana", "let=baya var=fetola fn=tiro if=fa else=eseng while=nako for=ka in=mo return=boelela true=boammaaruri false=bofodi null=sepe and=le or=kapa not=ga")
_RAW["ts"] = ("Xitsonga Tsonga", "let=vekela var=cinca fn=nzigetiyo if=loko else=kumbe while=nkarhi for=eka in=ka return=vuyela true=nkoka false=miholo null=nhova and=ni or=kumbe not=hinkwavo")
_RAW["ve"] = ("Tshivenḓa Venda", "let=vhea var=shandukisa fn=mushumo if=arali else=nanga while=tshifhinga for=kha in=ha return=vhusa true=zwavhudi false=zwisi null=tshisali and=na or=kana not=si")
_RAW["kg"] = ("Kikongo Kongo", "let=vanda var=tambula fn=kisalu if=kana else=kokve while=ntangu for=ba in=na return=vutuka true=ntoma false=ve null=koke and=ye or=to not=ka")
_RAW["sn"] = ("chiShona Shona", "let=isa var=shandura fn=basa if=kana else=kanaunge while=nguva for=pase in=pa return=dzoka true=chokwadi false=nhema null=chisinachinhu and=ne or=kana not=kwete")
_RAW["mi"] = ("Te Reo Māori Māori", "let=whakatau var=huri fn=mahi if=mena else=kaore while=iaia for=mo in=roto return=hoki true=pono false=teka null=kore and=me or=ranei not=ehara")
_RAW["haw"] = ("ʻŌlelo Hawaiʻi Hawaiian", "let=hoonoho var=loli fn=hana if=ina else=aiole while=inamana for=no in=iloko return=hoi true=oiaioo false=hewa null=ole and=a or=paha not=aole")
_RAW["la"] = ("Latina Latin", "let=esto var=mute fn=munus if=si else=alioquin while=dum for=per in=in return=redde true=verum false=falsum null=inane and=et or=aut not=non")

# The type-system words (struct/enum/impl/protocol) arrived after the packs,
# so they live in their own table: a pack may translate them, and a pack that
# does not simply keeps the English word.
_TYPE_WORDS = {
    "hinglish": ("dhancha", "soochi", "lagao", "niyam"),
    "hi": ("संरचना", "गणना", "कार्यान्वयन", "प्रोटोकॉल"),
    "ur": ("ڈھانچہ", "فہرست", "نفاذ", "ضابطہ"),
    "bn": ("গঠন", "গণনা", "বাস্তবায়ন", "প্রোটোকল"),
    "ta": ("அமைப்பு", "கணக்கு", "செயலாக்கம்", "நெறிமுறை"),
    "te": ("నిర్మాణం", "గణన", "అమలు", "ప్రోటోకాల్"),
    "ml": ("ഘടന", "ഗണന", "നടപ്പാക്കൽ", "പ്രോട്ടോക്കോൾ"),
    "kn": ("ರಚನೆ", "ಎಣಿಕೆ", "ಜಾರಿ", "ಪ್ರೋಟೋಕಾಲ್"),
    "mr": ("रचना", "गणना", "अंमल", "प्रोटोकॉल"),
    "gu": ("રચના", "ગણતરી", "અમલ", "પ્રોટોકોલ"),
    "pa": ("ਢਾਂਚਾ", "ਗਿਣਤੀ", "ਲਾਗੂ", "ਪ੍ਰੋਟੋਕੋਲ"),
    "es": ("estructura", "enumeracion", "implementa", "protocolo"),
    "fr": ("structure", "enumeration", "implante", "protocole"),
    "de": ("struktur", "aufzaehlung", "umsetzung", "protokoll"),
    "pt": ("estrutura", "enumeracao", "implementa", "protocolo"),
    "it": ("struttura", "enumerazione", "implementa", "protocollo"),
    "ru": ("структура", "перечисление", "реализация", "протокол"),
    "ar": ("هيكل", "تعداد", "تنفيذ", "بروتوكول"),
    "zh": ("结构", "枚举", "实现", "协议"),
    "zh_tw": ("結構", "列舉", "實作", "協定"),
    "ja": ("構造", "列挙", "実装", "プロトコル"),
    "ko": ("구조", "열거", "구현", "프로토콜"),
    "id": ("struktur", "enumerasi", "implementasi", "protokol"),
    "tr": ("yapi", "sayim", "uygulama", "protokol"),
    "vi": ("cau_truc", "liet_ke", "thuc_thi", "giao_thuc"),
    "th": ("โครงสร้าง", "การแจงนับ", "การนำไปใช้", "โปรโตคอล"),
    "pl": ("struktura", "wyliczenie", "implementacja", "protokol"),
    "nl": ("structuur", "opsomming", "implementatie", "protocol"),
    "fa": ("ساختار", "شمارش", "پیادهسازی", "پروتکل"),
    "he": ("מבנה", "מנייה", "מימוש", "פרוטוקול"),
    "sv": ("struktur", "upprakning", "implementering", "protokoll"),
    "uk": ("структура", "перелік", "реалізація", "протокол"),
    "el": ("δομή", "απαρίθμηση", "υλοποίηση", "πρωτόκολλο"),
    "af": ("struktuur", "opsomming", "implementasie", "protokol"),
    "bg": ("структура", "изброяване", "реализация", "протокол"),
    "ca": ("estructura", "enumeracio", "implementacio", "protocol"),
    "cs": ("struktura", "vycet", "implementace", "protokol"),
    "da": ("struktur", "optaelling", "implementering", "protokol"),
    "eo": ("strukturo", "enumeracio", "implemento", "protokolo"),
    "et": ("struktuur", "loend", "teostus", "protokoll"),
    "fi": ("rakenne", "luettelo", "toteutus", "protokolla"),
    "hr": ("struktura", "nabrajanje", "provedba", "protokol"),
    "hu": ("szerkezet", "felsorolas", "megvalositas", "protokoll"),
    "is": ("bygging", "talning", "framkvaemd", "samskiptaregla"),
    "lt": ("struktura", "sarasas", "igyvendinimas", "protokolas"),
    "lv": ("struktura", "uzskaitijums", "ieviesana", "protokols"),
    "no": ("struktur", "oppramsing", "implementering", "protokoll"),
    "ro": ("structura", "enumerare", "implementare", "protocol"),
    "sk": ("struktura", "vycet", "implementacia", "protokol"),
    "sl": ("struktura", "nastevanje", "izvedba", "protokol"),
    "sr": ("структура", "набрајање", "примена", "протокол"),
    "sw": ("muundo", "orodha", "utekelezaji", "itifaki"),
    "tl": ("istruktura", "enumerasyon", "pagpapatupad", "protokol"),
    "ms": ("struktur", "penghitungan", "pelaksanaan", "protokol"),
    "az": ("qurulus", "sayim", "tetbiq", "protokol"),
    "ka": ("სტრუქტურა", "ჩამოთვლა", "განხორციელება", "ოქმი"),
    "hy": ("կառուցվածք", "թվարկում", "իրականացում", "արձանագրություն"),
    "uz": ("tuzilma", "sanov", "amalga", "protokol"),
    "kk": ("құрылым", "санама", "орындалуы", "хаттама"),
}

_TYPE_SLOTS = ("struct", "enum", "impl", "protocol")

_CACHE = {}


def pack(lang):
    """(display name, {english: localized}) for one language code."""
    if lang not in _CACHE:
        entry = _RAW.get(lang)
        if entry is None:
            raise KeyError("unknown language pack: %s" % lang)
        table = parse_pack(entry[1])
        words = _TYPE_WORDS.get(lang)
        if words:
            taken = set(table.values())
            for slot, word in zip(_TYPE_SLOTS, words):
                if word and word not in taken:
                    table[slot] = word
                    taken.add(word)
        _CACHE[lang] = (entry[0], table)
    return _CACHE[lang]


def has_pack(lang):
    return lang in _RAW


def list_packs():
    """Every pack as (code, name, keyword count), sorted by code."""
    rows = []
    for code in sorted(_RAW):
        name, words = pack(code)
        rows.append((code, name, len(words)))
    return rows


def detect_directive(source):
    """The `#!lang xx` / `#lang: xx` directive on the first line, if any."""
    first = source.split("\n", 1)[0].strip()
    for prefix in ("#!lang ", "#lang:", "#lang "):
        if first.startswith(prefix):
            code = first[len(prefix):].strip()
            if code and has_pack(code):
                return code
    return None


def _script_words(source):
    """Split source into word tokens, keeping combining marks attached.

    `\w+` alone breaks Devanagari matras and Arabic harakat off their
    base letters, so "अन्यथा" would come out as fragments. This walker
    treats any letter/digit/underscore plus following marks as one word.
    """
    import unicodedata as _ud
    words, buf = [], ""
    for ch in source:
        keep = ch.isalnum() or ch == "_" or _ud.category(ch) in ("Mn", "Mc",
                                                                 "Me")
        if keep:
            buf += ch
        elif buf:
            words.append(buf)
            buf = ""
    if buf:
        words.append(buf)
    return words


def detect_auto(source, threshold=3):
    """Best-effort language detection by distinct localized keyword hits."""
    words = set(_script_words(source))
    best, best_hits = None, 0
    for code in sorted(_RAW):
        _, table = pack(code)
        hits = len(words & set(table.values()))
        if hits > best_hits:
            best, best_hits = code, hits
    return best if best_hits >= threshold else None
