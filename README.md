# Token Dashboard

Claude Code oturumlarının maliyetini ve bağlamını gösteren yerel bir pano. Şu sorulara cevap verir:
- Bu session ne kadar tuttu?
- Hangi prompt pahalıydı, neden?
- Bağlama neler girdi?
- Hangi dosyalar okundu, hangi MCP sunucuları ve URL'ler çağrıldı?
- Subagent'lar ne harcadı?
- Bir branch'teki iş kaça mal oldu ve kaç commit üretti?

Her şey bilgisayarında çalışır. İnternete bağlanmaz, telemetri göndermez, token harcamaz, `pip install` gerektirmez.

## Sayfalar

| Sayfa | Ne gösterir |
|---|---|
| **Overview** | Tarih aralığına göre toplam token ve maliyet, günlük grafikler, model ve proje dağılımı, en çok kullanılan tool'lar. **Subagents** bölümü: türüne göre maliyet (Explore, general-purpose, workflow…) ve en pahalı subagent çalıştırmaları. |
| **Sessions** | Başlığıyla birlikte session listesi; projeye göre filtrelenebilir. Bir session'a tıklayınca KPI kartları ve sekmeler açılır (aşağıda). |
| **Prompts** | Tüm session'lardaki en pahalı adımlar: gerçek maliyet, maliyetin nedeni (output / cache read / cache write) ve ⚠ cache rebuild uyarısı. Tarih, proje ve modele göre filtrelenir. |
| **Projects** | Proje başına token dağılımı. **Cost by project & branch** tablosu: branch başına maliyet, o branch'teki session'lar sırasında atılan commit'ler, eklenen/silinen satır, commit başına maliyet. |
| **Skills / Tips / Settings** | Skill kullanımı, tasarruf önerileri, plan seçimi. |

**Session sayfasının sekmeleri:**

| Sekme | Ne gösterir |
|---|---|
| Overview | Turn başına bağlam büyüklüğü grafiği, model başına maliyet |
| Steps | Yazdığın her prompt'un maliyeti, kaç turn sürdüğü, hangi tool'ları çağırdığı |
| Auto-loaded | Sen istemeden bağlama girenler: CLAUDE.md, rules ve hafıza dosyaları, skill'ler, hook çıktıları, MCP talimatları, tool ve skill listeleri |
| Tools | Tool başına çağrı, hata ve sonuç token'ı; en büyük 10 tool sonucu |
| Subagents | Session'daki her subagent çalıştırması: türü, açıklaması, maliyeti |
| Files | Okunan ve yazılan dosyalar |
| MCP & web | Çağrılan MCP sunucuları ve URL'ler |
| Turn-by-turn | Her kaydın token dökümü |

Her tablonun altında toplam satırı var. **⬇ export .md** session özetini Markdown dosyası olarak indirir; AI-DLC dokümanlarına doğrudan eklenebilir.

## Kurulum (Windows)

Python 3 gerekir. Git kuruluysa commit eşleştirmesi de çalışır.

```powershell
git clone https://github.com/hasan-ozturk/tokendashboard.git C:\Repos\tokendashboard
cd C:\Repos\tokendashboard
.\install.ps1                                   # http://localhost:8765
.\install.ps1 -HostName tdb.local -AutoStart    # http://tdb.local:8765, Windows açılışında başlar
```

Script şunları yapar:
1. Claude Code için `token-dashboard` skill'ini `~/.claude/skills/` altına kurar.
2. `-HostName` verilirse hosts dosyasına bir satır ekler. Bunun için Windows bir kez yönetici izni ister.
3. `-AutoStart` verilirse Startup klasörüne gizli bir başlatıcı koyar.
4. Panoyu başlatır.

İlk açılışta tüm transcript'ler taranır, bu bir dakika kadar sürebilir.

Script `ExecutionPolicy` hatası verirse şöyle çalıştır: `powershell -ExecutionPolicy Bypass -File .\install.ps1`.

## Kurulum (macOS / Linux)

```bash
cd tokendashboard
PORT=8765 python3 cli.py dashboard
```

Skill'i kullanmak için `skill/token-dashboard/SKILL.md` dosyasını `~/.claude/skills/token-dashboard/SKILL.md` konumuna kopyala ve içindeki `{{...}}` alanlarını doldur:

| Alan | Değer |
|---|---|
| `{{REPO_DIR}}` | reponun yolu |
| `{{BASE_URL}}` | `http://localhost:8765` |
| `{{PORT}}` | `8765` |
| `{{PYTHON}}` | `python3` |

## Kullanım

Claude Code'da "token dashboard" ya da "bu session'ın maliyeti" yaz. Claude panoyu kontrol eder, kapalıysa başlatır ve o anki session'ın linkini verir.

Doğrudan tarayıcıdan da açabilirsin: `http://localhost:8765` (ya da `http://tdb.local:8765`).

## Neyi görür, neyi görmez

| Kaynak | Görünür mü |
|---|---|
| Claude Code: VS Code ve Cursor eklentisi, terminal (CLI) | Evet |
| Claude Desktop'taki "Code" sekmesi | Muhtemelen evet (yerelde Claude Code çalıştırıyor) |
| Claude Desktop ve claude.ai'deki normal sohbetler | Hayır, bu sohbetler yerelde kayıt bırakmıyor |
| Cursor'ın kendi Chat ve Agent ekranları | Hayır |

## Bilmen gerekenler

- **Maliyetler API liste fiyatlarıyla hesaplanır** (`pricing.json`). Abonelik planındaysan bu tutarı ayrıca ödemezsin; rakam, API'den kullansaydın ne ödeyeceğini gösterir.
- **Bazı token sayıları tahmindir.** Tool sonuçları ve otomatik yüklenen içerik için gösterilen sayılar karakter sayısı / 4 ile hesaplanır.
- **Commit eşleştirmesi zamana göredir.** Senin git kullanıcının, bir session sırasında ya da session bitiminden sonraki 1 saat içinde attığı commit'ler sayılır. Aynı zaman aralığında elle atılan commit'ler de bu sayıya girer. Satır sayılarına üretilmiş ve kütüphane dosyaları da dahildir.
- **Cache rebuild:** Bir turn'de bağlamın 100K token'dan fazlası cache'e yeniden yazılırsa ⚠ ile işaretlenir. Bu genelde 1 saatten uzun aradan sonra eski bir session'a dönünce ya da model değiştirince olur. Yeni session açmak ya da önce `/compact` çalıştırmak daha ucuzdur.
- **Gizlilik:** Pano prompt metinlerini okur ve yerel veritabanında tutar, ama hiçbir yere göndermez. Veritabanı `~/.claude/token-dashboard.db` dosyasıdır; silersen bir sonraki açılışta transcript'ler baştan taranır.
- **Gecikme:** Yeni turn'ler panoya 30 saniye içinde düşer.

## Testler

```bash
python -m unittest discover -s tests
```

## Kaynak

[nateherkai/token-dashboard](https://github.com/nateherkai/token-dashboard) projesinden türetilmiştir (MIT lisansı, bkz. `LICENSE`). Orijinal README: [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md). Branch maliyeti ve subagent kırılımı fikirleri [phuryn/claude-usage](https://github.com/phuryn/claude-usage) ve [xiufengsun/TokenTracker](https://github.com/xiufengsun/TokenTracker) projelerinden alındı.

Bu fork'ta eklenenler:
- Session özeti, sekmeleri ve dip toplamları
- Prompt ve adım başına maliyet, cache rebuild tespiti
- Otomatik yüklenen bağlamın dökümü
- Proje + branch maliyeti ve commit eşleştirmesi
- Subagent türüne ve çalıştırmaya göre maliyet
- `.md` dışa aktarma, session başlıkları, projeden session'lara filtreli geçiş
- Claude Code skill'i ve Windows kurulum script'i
- Güncel model fiyatları (Fable, Opus 5.5, Sonnet 5.5, Haiku 5.5)
- Büyük veritabanlarında tarama hızını düzelten bir index
- Plan seçiminin tarayıcı yerine veritabanında saklanması
