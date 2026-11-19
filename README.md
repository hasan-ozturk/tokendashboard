# Token Dashboard

Claude Code oturumlarının maliyetini ve bağlamını gösteren yerel bir pano. Her session için şunları görürsün:

- Model başına maliyet, input, output ve cache token'ları
- **Steps:** yazdığın her prompt'un maliyeti, kaç turn sürdüğü ve hangi tool'ları çağırdığı
- **Auto-loaded:** bağlama kendiliğinden girenler: CLAUDE.md, rules ve hafıza dosyaları, skill'ler, hook çıktıları, MCP talimatları
- Okunan ve yazılan dosyalar, çağrılan MCP sunucuları ve URL'ler, en büyük tool sonuçları
- Turn başına bağlam büyüklüğü grafiği
- Session özetini `.md` olarak dışa aktarma

**Prompts** sayfası tüm session'lardaki en pahalı adımları listeler. Proje, model ve tarihe göre filtrelenebilir. Bağlamın baştan cache'e yazıldığı adımları ⚠ ile işaretler; bu genelde uzun aradan sonra eski bir session'a dönünce olur.

Her şey bilgisayarında çalışır. Pano yalnızca Claude Code'un `~/.claude/projects/` altına yazdığı transcript dosyalarını okur. İnternete bağlanmaz, token harcamaz, `pip install` gerektirmez.

## Kurulum (Windows)

Python 3 gerekir.

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

- Maliyetler API liste fiyatlarıyla hesaplanır (`pricing.json`). Abonelik planındaysan bu tutarı ayrıca ödemezsin; rakam, API'den kullansaydın ne ödeyeceğini gösterir.
- Tool sonuçları ve otomatik yüklenen içerik için gösterilen token sayıları tahmindir: karakter sayısı / 4.
- Yeni turn'ler panoya 30 saniye içinde düşer.
- Veritabanı `~/.claude/token-dashboard.db` dosyasıdır. Silersen bir sonraki açılışta transcript'ler baştan taranır.

## Testler

```bash
python -m unittest discover -s tests
```

## Kaynak

[nateherkai/token-dashboard](https://github.com/nateherkai/token-dashboard) projesinden türetilmiştir (MIT lisansı, bkz. `LICENSE`). Orijinal README: [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md).

Bu fork'ta eklenenler:
- Session özeti, sekmeleri ve dip toplamları
- Prompt ve adım başına maliyet
- Otomatik yüklenen bağlamın dökümü
- `.md` dışa aktarma
- Session başlıkları
- Projeden session'lara filtreli geçiş
- Güncel model fiyatları (Fable, Opus 5.5, Sonnet 5.5, Haiku 5.5)
- Büyük veritabanlarında tarama hızını düzelten bir index
- Plan seçiminin tarayıcı yerine veritabanında saklanması
