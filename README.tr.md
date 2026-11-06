<p align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Issue Radar logosu">
</p>

<h1 align="center">Issue Radar</h1>

<p align="center"><strong>Bir sonraki açık kaynak katkını, başkası kapmadan bul.</strong></p>

<p align="center">
  <a href="https://github.com/fefezey/issue-radar/actions/workflows/tests.yml"><img src="https://github.com/fefezey/issue-radar/actions/workflows/tests.yml/badge.svg" alt="Testler"></a>
  · <a href="README.md">English</a>
</p>

Issue Radar, GitHub'da yeni başlayanlara uygun işleri bulmana yardım eder.

GitHub'ı yeni işler için tarar, başkasının çoktan aldığı işleri ayıklar ve bakmaya değer bir şey bulduğunda sana haber verir. Hangi programlama dillerini takip edeceğini seçebilir, işleri projelere göre inceleyebilir ve katkılarını takip edebilirsin. İstersen Ollama üzerinden yapay zeka özetleri de alırsın; böylece bir işe başlamadan önce ne istendiğini anlarsın.

Her şey kendi Mac'inde çalışır. Verilerin ve tercihlerin bilgisayarında kalır.

## Neler yapıyor

- 🔍 **Yeni başlangıç işlerini bulur.** Seçtiğin dillerde, en yeniden başlayarak. Şu etiketlere bakar: `good first issue`, `good-first-issue`, `first-timers-only`, `beginner`, `beginner-friendly`.
- 🧭 **"Bu proje yeni gelenlere açık mı?" sorusunu cevaplar.** Her projenin ne olduğu tek satırla yazılır, yanında da son üç ayda ekip dışından kaç PR birleştirdiği görünür. Hiç birleştirmemiş projeler işaretlenir.
- 🗂️ **İşleri projelere göre gruplar.** Tek bir kalabalık proje bütün listeyi dolduramaz; aynı projenin diğer işleri "Bu projeden N iş daha" satırının altında toplanır.
- ⭐ **Çok küçük projeleri göstermez.** Varsayılan olarak en az 100 yıldızı olan projeler listelenir; bunu ayarlardan değiştirebilirsin.
- 🌱 **Önce yeni projeler.** Henüz PR göndermediğin projelerin işleri listenin başında yer alır. Daha önce katkı yaptığın projeler ayrıca işaretlenir.
- ⚡ **Alınmış işleri ayıklar.** Birine atanmış, bağlı bir PR'ı olan ya da yorumlarda biri "bu işi ben yapmak istiyorum" demiş işler listeye girmez. Kaydedilen işler her taramada yeniden kontrol edilir; sonradan kapanan ya da başkasının aldığı işler de listeden düşer.
- 🤖 **Ücretsiz ve gizli yapay zeka özetleri.** Bilgisayarında çalışan küçük bir model ([Ollama](https://ollama.com) üzerinden) her işi senin dilinde iki cümleyle anlatır. İsteğe bağlıdır; kurmazsan uygulama özetsiz çalışır.
- 📄 **Doküman, test ve çeviri işlerini işaretler.** İlk katkı için en rahat işler bunlardır. İşin başlığından ve GitHub etiketlerinden bulunur; yalnızca bunları gösteren bir filtre de var.
- 🔔 **Mac bildirimleri.** 10 dakikada bir tarar, en fazla saatte bir bildirim gönderir.
- 🖥️ **Sade bir web sayfası.** İşleri gözden geçirirsin: *İlgileniyorum*, *Geç* ya da *Projeyi gizle*. Her şey geri alınabilir ve sayfa kaldığın yerden kaymaz.
- ✍️ **İşi istemek için hazır yorum.** *İlgileniyorum*'a basınca gönderilmeye hazır bir yorum taslağı açılır ("I'd like to work on this… could you assign it to me?"). İçinde kendi planını yazacağın bir satır ve yorumu kopyalayıp işi GitHub'da açan bir düğme var. Projenin katkı rehberi "sormadan doğrudan PR aç" diyorsa bunu da söyler.
- 🧗 **İlerlemeni takip eder.** İlgilendiğin işler için GitHub'ı her taramada okur ve nerede olduğunu gösterir: *Yorum yazdın → Atandın → PR açtın → Birleşti*. Her aşamada sıradaki adımı da yazar; PR'ını işe bağlayan `Fixes #123` satırı dahil. Sana iş atandığında, PR'ın birleştiğinde ya da istediğin işi başkası aldığında Mac bildirimi gelir.
- 🗺️ **Nereden başlayacağını gösterir.** İlgilendiğin her iş için bir rehber açılır: işte adı geçen ve projede gerçekten var olan dosyalar (linkleriyle), projenin katkı rehberinden ve README'sinden çıkarılan kurulum ve test komutları, bir de yapay zekanın yazdığı sade bir açıklama.
- ⚙️ **Ayarlar sayfası.** Hangi dillerde arama yapılacağını ve en az kaç yıldız isteneceğini seçersin.
- 🌍 **Türkçe ve İngilizce arayüz.** Tarayıcının dilini kendisi seçer, istediğin zaman değiştirebilirsin. Bildirimler de aynı dilde gelir.
- 🌗 **Açık ve koyu tema.** Sistemine uyar.

### Planlananlar

- [ ] Bakımcıların yeni gelenlere ne kadar hızlı cevap verdiği
- [ ] Daha fazla arayüz dili ([kendi dilini ekle](#dil-ekle))
- [ ] Linux ve Windows bildirimleri
- [ ] Telegram ve Discord bildirimleri

## Nasıl çalışıyor

1. **Tarar.** 10 dakikada bir GitHub'da başlangıç etiketi taşıyan yeni, açık işleri arar.
2. **Ayıklar.** Atanmış, bağlı PR'ı olan, yorumlarda alınmış ya da yıldızı az projelerden gelen işleri eler. Projelerin yıldız sayılarını bir gün boyunca hatırlar, böylece GitHub'a her taramada yeniden sormaz.
3. **Yeniden kontrol eder.** Kayıtlı en fazla 20 işe tek bir istekle tekrar bakar; o arada kapanan ya da başkasının aldığı işleri listeden çıkarır.
4. **Projeleri tanır.** Her taramada birkaç proje için, her birine günde en fazla bir kez bakar: proje ne işe yarıyor, son zamanlarda ekip dışından kaç PR birleştirmiş (botlar sayılmaz).
5. **Özetler.** Ollama çalışıyorsa her yeni işe arka planda, sırayla kısa bir özet yazar. Açıklaması çok kısa işlere özet yazmaz, çünkü başlık zaten yeterince şey söylüyor.
6. **Haber verir.** Yeni işleri bilgisayarına kaydeder ve Mac'inde bildirim gösterir.
7. **Sen karar verirsin.** Web sayfasını açıp üzerinde çalışmak istediğin işi seçersin.

## Kurulum

[uv](https://docs.astral.sh/uv/) gerekiyor; doğru Python sürümünü de o kuruyor:

```bash
brew install uv
```

Sonra:

```bash
git clone https://github.com/fefezey/issue-radar.git
cd issue-radar
uv run issue-radar
```

Tarayıcıda **http://localhost:8000** adresini aç. İlk tarama bir dakika kadar sürebilir; sayfa kendiliğinden yenilenir.

### Yapay zeka özetleri (isteğe bağlı)

Özetleri [Ollama](https://ollama.com) üzerinden `gemma3:4b` modeli yazıyor (yaklaşık 3 GB). Ücretsiz, ve işlerin metni bilgisayarından hiç çıkmıyor:

```bash
brew install ollama
brew services start ollama
ollama pull gemma3:4b
```

Issue Radar Ollama'yı kendisi fark eder; özetlerin açık olup olmadığını **Ayarlar** sayfasında görebilirsin. Model 8 GB belleği olan bir Mac'te çalışıyor, ama özetler yavaş gelirse iOS Simülatörü gibi ağır uygulamaları kapat. Başka bir model kullanmak istersen `OLLAMA_MODEL` ayarını değiştir, örneğin: `OLLAMA_MODEL=qwen2.5:3b uv run issue-radar`.

Özetleri küçük bir model yazıyor ve yanılabiliyor; işin aslı her zaman bir tık uzağında.

### GitHub erişimi

GitHub, giriş yapmadan saatte yalnızca 60 isteğe izin veriyor; bu yetmez. Issue Radar sırasıyla şunları kullanır:

1. Ayarlanmışsa `GITHUB_TOKEN` ortam değişkenini,
2. yoksa [GitHub CLI](https://cli.github.com/) girişini (`gh auth login`).

Token'ın yalnızca herkese açık verileri okuyabilmesi yeterli.

### Bildirimler

macOS'ta bildirimler AppleScript ile gösterildiği için **Script Editor**'den (Betik Düzenleyicisi) geliyormuş gibi görünür. Bildirim görmüyorsan **Sistem Ayarları → Bildirimler** bölümünden Script Editor'e izin ver.

## Ayarlar

Sayfadaki **Ayarlar** bölümünden şunları seçebilirsin:

- **Taranacak diller:** Python, JavaScript, TypeScript, Go, Rust, Java, C#, C++, Ruby, PHP, Kotlin, Swift. Varsayılan: Python ve JavaScript.
- **En az yıldız:** Fark etmez, 50, 100, 500 ya da 1000. Varsayılan: 100.

Değişiklikler hemen uygulanır ve yeni bir tarama başlar.

Şunlar şimdilik kodun içinde, `src/issue_radar/scanner.py` dosyasında:

| Ne | Adı | Varsayılan |
| --- | --- | --- |
| Tarama sıklığı | `SCAN_INTERVAL` | 10 dakika |
| Başarısız taramadan sonra tekrar deneme | `RETRY_INTERVAL` | 5 dakika |
| Bildirim sıklığı | `NOTIFY_INTERVAL` | 1 saat |

İşlerin ve tercihlerin `~/.issue-radar/issues.db` dosyasında duruyor. Sıfırdan başlamak istersen bu dosyayı silmen yeterli.

## Proje yapısı

```
src/issue_radar/
├── __init__.py      tarayıcıyı ve web sayfasını başlatır
├── github.py        GitHub'la konuşur: arama, yıldızlar, alınmış işler, senin PR'ların
├── scanner.py       düzenli tarar ve ne zaman bildirim gideceğine karar verir
├── ai.py            Ollama ile yapay zeka özetleri
├── kinds.py         doküman, test ve çeviri işlerini tanır
├── claiming.py      yorum taslağı ve katkı rehberlerini okuma
├── guide.py         iş rehberi: kurulum ve test komutları, bakılacak dosyalar
├── notify.py        Mac bildirimleri
├── db.py            yerel SQLite veritabanı
├── web.py           web sayfasının adresleri
├── languages.py     aranabilecek diller ve görünen adları
├── settings.py      ayarlar sayfasındaki ayarlar
├── i18n.py          çeviriler
├── locales/         her arayüz dili için bir JSON dosyası
└── templates/
    └── index.html   web sayfası
```

## Katkı

Katkılarını bekliyoruz; ne de olsa bu, ilk katkısını yapacaklar için yapılmış bir araç. Başlamak için iyi yerler:

- **Bir dil ekle.** Aşağıda anlatılıyor; kod bilmen gerekmiyor.
- **Alınmış işleri daha iyi tanı.** `github.py` içindeki `CLAIM_PHRASES`, insanların bir işi alırken yazdığı cümleleri listeliyor. Karşına çıkanları ekleyebilirsin.
- **Daha fazla kolay iş türü yakala.** `kinds.py`, başlıklardan ve etiketlerden doküman, test ve çeviri işlerini buluyor. Kaçırdığı ya da yanlış eşleştirdiği bir iş mi gördün? Kuralları düzelt.
- **Linux ya da Windows bildirimleri.** `notify.py` şimdilik yalnızca macOS'u destekliyor.
- **[Planlananlar](#planlananlar) listesindeki herhangi bir madde.**

Büyük bir değişiklik düşünüyorsan önce bir issue aç.

### Testleri çalıştır

```bash
uv run pytest
```

Testler için internet, GitHub token'ı ya da Ollama gerekmiyor: GitHub'ın ve modelin cevapları testlerin içinde taklit ediliyor, her test de kendi boş veritabanını kullanıyor. Testler her push'ta ve her PR'da otomatik çalışıyor.

### Dil ekle

1. `src/issue_radar/locales/en.json` dosyasını kendi dil kodunla adlandırılmış yeni bir dosyaya kopyala, örneğin `de.json`.
2. Sağdaki metinleri çevir. Soldaki anahtarlara ve `{süslü parantez}` içindeki yer tutuculara dokunma.
3. Sayıyla değişen kelimeler için `.one` ve `.other` anahtarlarını kullan, örneğin `"issue.stars.one": "{stars} star"` ve `"issue.stars.other": "{stars} stars"`. Dilinde kelime sayıyla değişmiyorsa yalnızca `.other` yeterli.
4. `uv run issue-radar` ile programı başlat ve sağ üst köşeden dilini seç.

Çevirmediğin metinler İngilizce görünür.

## Lisans

[MIT](LICENSE)

---

<p align="center"><em>Daha çok katkı, daha az arama.</em></p>
