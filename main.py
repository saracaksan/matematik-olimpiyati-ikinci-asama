from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import random
import csv
import io

# ==========================================
# 1. VERİTABANI BAĞLANTISI
# ==========================================
DATABASE_URL = "sqlite:///./olimpiyat.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

YONETICI_SIFRE = "Sarac.47"
OGRETMEN_SIFRE = "darder.47"

class SistemAyar(Base):
    __tablename__ = "sistem_ayarlari"
    ayar_adi = Column(String, primary_key=True, index=True)
    ayar_degeri = Column(Boolean, default=False)

class Ogrenci(Base):
    __tablename__ = "ogrenciler"
    id = Column(Integer, primary_key=True, index=True)
    okul = Column(String, index=True)
    sinif_seviyesi = Column(Integer, index=True)
    sube = Column(String, nullable=True) 
    ogrenci_no = Column(String, nullable=True)
    ad_soyad = Column(String, index=True)
    birinci_asama_puani = Column(Float, nullable=True) 
    
    asil_puan = Column(Float, default=0.0)
    yedek_puan = Column(Float, default=0.0)
    kura_degeri = Column(Integer, default=lambda: random.randint(1, 1000000))
    degerlendiren_ogretmen = Column(String, nullable=True)
    yanitlar = relationship("Yanit", back_populates="ogrenci", cascade="all, delete")

class Soru(Base):
    __tablename__ = "sorular"
    id = Column(Integer, primary_key=True, index=True)
    sinif_seviyesi = Column(Integer, index=True)
    soru_tipi = Column(String)  
    soru_no = Column(Integer)
    puan_degeri = Column(Float)
    dogru_cevap_metni = Column(String, nullable=True) 
    yanitlar = relationship("Yanit", back_populates="soru", cascade="all, delete")

class Yanit(Base):
    __tablename__ = "yanitlar"
    id = Column(Integer, primary_key=True, index=True)
    ogrenci_id = Column(Integer, ForeignKey("ogrenciler.id"))
    soru_id = Column(Integer, ForeignKey("sorular.id"))
    dogru_mu = Column(Boolean) 
    ogrenci = relationship("Ogrenci", back_populates="yanitlar")
    soru = relationship("Soru", back_populates="yanitlar")

class LoginRequest(BaseModel):
    sifre: str
    ogretmen_ad_soyad: Optional[str] = None

class YeniOgrenciRequest(BaseModel):
    sifre: str
    ad_soyad: str
    okul: str
    sinif: int
    sube: str
    birinci_asama_puani: Optional[float] = None
    zorla_kaydet: bool = False  # Çift kayıtta 'Evet' denirse True gelir

class OgrenciGuncelleRequest(BaseModel):
    sifre: str
    ad_soyad: str
    okul: str
    sinif_seviyesi: int
    sube: str

class YanitGiris(BaseModel):
    soru_id: int
    dogru_mu: bool

class DegerlendirmeRequest(BaseModel):
    ogrenci_id: int
    yanitlar: List[YanitGiris]
    ogretmen_ad_soyad: str

class SoruGuncelleRequest(BaseModel):
    sifre: str
    soru_id: int
    yeni_puan: Optional[float] = None
    yeni_cevap: Optional[str] = None

class SoruEkleRequest(BaseModel):
    sifre: str
    sinif_seviyesi: int
    soru_tipi: str
    puan_degeri: float

app = FastAPI(title="MEB 1. Matematik Olimpiyatı Arka Plan Sistemi")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
Base.metadata.create_all(bind=engine)

@app.on_event("startup")
def baslangic_verilerini_yukle():
    db = SessionLocal()
    if db.query(SistemAyar).filter(SistemAyar.ayar_adi == "sistem_kilitli").first() is None:
        db.add(SistemAyar(ayar_adi="sistem_kilitli", ayar_degeri=False))
    
    siniflar = [4, 5, 6, 7, 8, 9, 10, 11, 12]
    if db.query(Soru).first() is None:
        for s in siniflar:
            # Asil Sorular (10 Soru)
            for i in range(1, 11):
                puan = 3.0 if i <= 4 else (4.0 if i <= 7 else 5.0)
                db.add(Soru(sinif_seviyesi=s, soru_tipi="asil", soru_no=i, puan_degeri=puan, dogru_cevap_metni=""))
            # Yedek Sorular (İlk 2 soru 4 Puan, Son 3 soru 5 Puan)
            for i in range(1, 6):
                puan = 4.0 if i <= 2 else 5.0
                db.add(Soru(sinif_seviyesi=s, soru_tipi="yedek", soru_no=i, puan_degeri=puan, dogru_cevap_metni=""))
    db.commit()
    db.close()

# ==========================================
# GİRİŞ VE KİLİT UÇLARI
# ==========================================
@app.post("/api/login")
def sisteme_giris(req: LoginRequest):
    if req.sifre == YONETICI_SIFRE: return {"rol": "yonetici"}
    elif req.sifre == OGRETMEN_SIFRE:
        if not req.ogretmen_ad_soyad: raise HTTPException(status_code=400, detail="Lütfen ad soyad giriniz.")
        return {"rol": "ogretmen", "ogretmen_adi": req.ogretmen_ad_soyad}
    raise HTTPException(status_code=401, detail="Hatalı şifre!")

@app.get("/api/sistem/kilit_durumu")
def kilit_durumu():
    db = SessionLocal()
    ayar = db.query(SistemAyar).filter(SistemAyar.ayar_adi == "sistem_kilitli").first()
    db.close()
    return {"kilitli": ayar.ayar_degeri if ayar else False}

@app.post("/api/yonetici/kilit_guncelle")
def kilit_guncelle(sifre: str, kilitli_mi: bool):
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ayar = db.query(SistemAyar).filter(SistemAyar.ayar_adi == "sistem_kilitli").first()
    ayar.ayar_degeri = kilitli_mi
    db.commit()
    db.close()
    return {"mesaj": "Sistem güncellendi."}

# ==========================================
# YÖNETİCİ: ÖĞRENCİ YÖNETİMİ (MANUEL LİSTE, SİLME, DÜZENLEME VE ÇİFT KAYIT)
# ==========================================

@app.post("/api/yonetici/ogrenci_ekle")
def ogrenci_ekle_manuel(req: YeniOgrenciRequest):
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    
    # Çift kayıt uyarısı algoritması
    if not req.zorla_kaydet:
        mevcut = db.query(Ogrenci).filter(Ogrenci.ad_soyad == req.ad_soyad, Ogrenci.sinif_seviyesi == req.sinif).first()
        if mevcut:
            db.close()
            return {"status": "uyari", "mesaj": f"Sistemde {req.sinif}. Sınıfta {req.ad_soyad} isimli bir öğrenci zaten var! Yine de eklemek ister misiniz?"}
            
    yeni_ogr = Ogrenci(ad_soyad=req.ad_soyad, okul=req.okul, sinif_seviyesi=req.sinif, sube=req.sube, birinci_asama_puani=req.birinci_asama_puani)
    db.add(yeni_ogr)
    db.commit()
    db.close()
    return {"status": "basarili", "mesaj": f"{req.ad_soyad} sisteme kaydedildi."}

@app.get("/api/yonetici/tum_ogrenciler")
def yonetici_ogrenci_listesi(sifre: str):
    """Yöneticinin düzenlemesi için tüm öğrenci listesini verir."""
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogrenciler = db.query(Ogrenci).order_by(Ogrenci.sinif_seviyesi.asc(), Ogrenci.ad_soyad.asc()).all()
    db.close()
    return ogrenciler

@app.delete("/api/yonetici/ogrenci_sil/{ogrenci_id}")
def yonetici_ogrenci_sil(ogrenci_id: int, sifre: str):
    """Yöneticinin öğrenciyi sistemden tamamen silmesi."""
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogrenci = db.query(Ogrenci).filter(Ogrenci.id == ogrenci_id).first()
    if not ogrenci: raise HTTPException(status_code=404)
    db.delete(ogrenci)
    db.commit()
    db.close()
    return {"mesaj": "Öğrenci sistemden TAMAMEN SİLİNDİ."}

@app.put("/api/yonetici/ogrenci_guncelle/{ogrenci_id}")
def yonetici_ogrenci_bilgi_guncelle(ogrenci_id: int, req: OgrenciGuncelleRequest):
    """Yöneticinin öğrencinin ismini, okulunu vs. değiştirmesi."""
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogrenci = db.query(Ogrenci).filter(Ogrenci.id == ogrenci_id).first()
    if not ogrenci: raise HTTPException(status_code=404)
    ogrenci.ad_soyad = req.ad_soyad
    ogrenci.okul = req.okul
    ogrenci.sinif_seviyesi = req.sinif_seviyesi
    ogrenci.sube = req.sube
    db.commit()
    db.close()
    return {"mesaj": "Öğrenci bilgileri güncellendi."}

@app.post("/api/yonetici/ogrenci_yukle_csv")
async def ogrenci_yukle_csv(file: UploadFile = File(...)):
    contents = await file.read()
    csv_reader = csv.reader(io.StringIO(contents.decode('utf-8-sig')), delimiter=',') 
    veri = list(csv_reader)
    if len(veri) > 0 and len(veri[0]) < 3:
        csv_reader = csv.reader(io.StringIO(contents.decode('utf-8-sig')), delimiter=';')
        veri = list(csv_reader)

    db = SessionLocal()
    eklenen = 0
    atlanan = 0
    for row in veri[1:]:
        if len(row) >= 5:
            okul = row[0].strip()
            ad_soyad = row[1].strip()
            sinif_sube = row[2].strip().split('/')
            sinif = int(sinif_sube[0].strip()) if sinif_sube[0].strip().isdigit() else 0
            sube = sinif_sube[1].strip() if len(sinif_sube) > 1 else ""
            ogrenci_no = row[3].strip()
            puan_str = row[4].strip().replace(',', '.')
            birinci_asama = float(puan_str) if puan_str else None

            if sinif > 0 and ad_soyad:
                # Toplu yüklemede çiftleri otomatik atlar, böylece aynı excel yüklenirse bozulmaz.
                mevcut = db.query(Ogrenci).filter(Ogrenci.ad_soyad == ad_soyad, Ogrenci.sinif_seviyesi == sinif).first()
                if mevcut:
                    atlanan += 1
                    continue
                    
                db.add(Ogrenci(okul=okul, ad_soyad=ad_soyad, sinif_seviyesi=sinif, sube=sube, ogrenci_no=ogrenci_no, birinci_asama_puani=birinci_asama))
                eklenen += 1
    db.commit()
    db.close()
    return {"mesaj": f"{eklenen} yeni öğrenci eklendi. (Zaten var olan {atlanan} öğrenci atlandı.)"}

# ==========================================
# YÖNETİCİ: RAPORLAMA VE SORULAR
# ==========================================
@app.get("/api/yonetici/detayli_rapor")
def yonetici_detayli_rapor(sifre: str):
    """Sadece Asil puanı EŞİT olanlarda Yedek'in devreye girdiğini açıkça raporlar."""
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    siniflar = db.query(Ogrenci.sinif_seviyesi).distinct().order_by(Ogrenci.sinif_seviyesi).all()
    siniflar = [s[0] for s in siniflar if s[0]]
    
    rapor = {}
    for sinif in siniflar:
        ogrenciler = db.query(Ogrenci).filter(Ogrenci.sinif_seviyesi == sinif, Ogrenci.degerlendiren_ogretmen.isnot(None)).order_by(Ogrenci.asil_puan.desc(), Ogrenci.yedek_puan.desc(), Ogrenci.kura_degeri.desc()).all()
        sinif_sonuclari = []
        for i, ogr in enumerate(ogrenciler):
            esitlik_durumu = False
            kura_durumu = False
            
            # Beraberlik Kontrolü (Asil puanı kimlerle eşit?)
            if i > 0 and ogr.asil_puan == ogrenciler[i-1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == ogrenciler[i-1].yedek_puan: kura_durumu = True
            if i < len(ogrenciler)-1 and ogr.asil_puan == ogrenciler[i+1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == ogrenciler[i+1].yedek_puan: kura_durumu = True
                
            durum_metni = "Net Asil Puan"
            if esitlik_durumu and not kura_durumu: durum_metni = "Yedek Puan İle Belirlendi"
            if kura_durumu: durum_metni = "Otomatik Kurayla Belirlendi"
                
            sinif_sonuclari.append({
                "id": ogr.id, "sira": i + 1, "ad_soyad": ogr.ad_soyad, "okul": ogr.okul, "sube": ogr.sube,
                "asil_puan": ogr.asil_puan, "yedek_puan": ogr.yedek_puan, "durum": durum_metni, "ogretmen": ogr.degerlendiren_ogretmen
            })
        rapor[f"{sinif}. Sınıflar"] = sinif_sonuclari
    db.close()
    return rapor

@app.post("/api/yonetici/soru_guncelle")
def soru_guncelle(req: SoruGuncelleRequest):
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    soru = db.query(Soru).filter(Soru.id == req.soru_id).first()
    if req.yeni_puan is not None: soru.puan_degeri = req.yeni_puan
    if req.yeni_cevap is not None: soru.dogru_cevap_metni = req.yeni_cevap
    db.commit()
    db.close()
    return {"mesaj": "Soru başarıyla güncellendi."}

@app.post("/api/yonetici/soru_ekle")
def soru_ekle(req: SoruEkleRequest):
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    mevcut_sayi = db.query(Soru).filter(Soru.sinif_seviyesi == req.sinif_seviyesi, Soru.soru_tipi == req.soru_tipi).count()
    db.add(Soru(sinif_seviyesi=req.sinif_seviyesi, soru_tipi=req.soru_tipi, soru_no=mevcut_sayi+1, puan_degeri=req.puan_degeri, dogru_cevap_metni=""))
    db.commit()
    db.close()
    return {"mesaj": f"{req.sinif_seviyesi}. Sınıflar için yeni {req.soru_tipi} soru eklendi."}

@app.get("/api/sorular/{sinif_seviyesi}")
def sorulari_getir(sinif_seviyesi: int):
    db = SessionLocal()
    sorular = db.query(Soru).filter(Soru.sinif_seviyesi == sinif_seviyesi).order_by(Soru.soru_tipi.asc(), Soru.soru_no.asc()).all()
    db.close()
    return sorular

# ==========================================
# ÖĞRETMEN DEĞERLENDİRME
# ==========================================
@app.post("/api/ogretmen/degerlendir")
def kagit_oku(req: DegerlendirmeRequest):
    db = SessionLocal()
    kilit = db.query(SistemAyar).filter(SistemAyar.ayar_adi == "sistem_kilitli").first()
    if kilit and kilit.ayar_degeri:
        db.close()
        raise HTTPException(status_code=403, detail="SİSTEM KİLİTLİ.")

    ogrenci = db.query(Ogrenci).filter(Ogrenci.id == req.ogrenci_id).first()
    if not ogrenci: raise HTTPException(status_code=404)
    if ogrenci.degerlendiren_ogretmen and ogrenci.degerlendiren_ogretmen != req.ogretmen_ad_soyad:
        db.close()
        raise HTTPException(status_code=403, detail=f"Kağıt {ogrenci.degerlendiren_ogretmen} tarafından okunmuş!")

    asil_toplam, yedek_toplam = 0.0, 0.0
    for yanit in req.yanitlar:
        soru = db.query(Soru).filter(Soru.id == yanit.soru_id).first()
        if yanit.dogru_mu:
            if soru.soru_tipi == "asil": asil_toplam += soru.puan_degeri
            elif soru.soru_tipi == "yedek": yedek_toplam += soru.puan_degeri
                
        mevcut_yanit = db.query(Yanit).filter(Yanit.ogrenci_id == ogrenci.id, Yanit.soru_id == soru.id).first()
        if mevcut_yanit: mevcut_yanit.dogru_mu = yanit.dogru_mu
        else: db.add(Yanit(ogrenci_id=ogrenci.id, soru_id=soru.id, dogru_mu=yanit.dogru_mu))

    ogrenci.asil_puan = asil_toplam
    ogrenci.yedek_puan = yedek_toplam
    ogrenci.degerlendiren_ogretmen = req.ogretmen_ad_soyad
    db.commit()
    db.close()
    return {"mesaj": "Kayıt Başarılı!"}

@app.delete("/api/ogretmen/ogrenci_sifirla/{ogrenci_id}")
def ogrenci_sifirla(ogrenci_id: int, ogretmen_ad: str):
    db = SessionLocal()
    kilit = db.query(SistemAyar).filter(SistemAyar.ayar_adi == "sistem_kilitli").first()
    if kilit and kilit.ayar_degeri:
        db.close()
        raise HTTPException(status_code=403, detail="Sistem Kilitli!")
        
    ogrenci = db.query(Ogrenci).filter(Ogrenci.id == ogrenci_id).first()
    if ogrenci.degerlendiren_ogretmen and ogrenci.degerlendiren_ogretmen != ogretmen_ad:
        db.close()
        raise HTTPException(status_code=403, detail="Sadece okuyan öğretmen silebilir!")
        
    db.query(Yanit).filter(Yanit.ogrenci_id == ogrenci_id).delete()
    ogrenci.asil_puan = 0.0
    ogrenci.yedek_puan = 0.0
    ogrenci.degerlendiren_ogretmen = None
    db.commit()
    db.close()
    return {"mesaj": "Öğrenci verileri sıfırlandı."}

# ==========================================
# PUBLIC UÇLAR VE LİSTELER
# ==========================================
@app.get("/api/public/okullar")
def okullari_getir():
    db = SessionLocal()
    okullar = db.query(Ogrenci.okul).distinct().all()
    db.close()
    return [o[0] for o in okullar if o[0]]

@app.get("/api/public/siniflar")
def siniflari_getir(okul_adi: str):
    db = SessionLocal()
    siniflar = db.query(Ogrenci.sinif_seviyesi).filter(Ogrenci.okul == okul_adi).distinct().all()
    db.close()
    return sorted([s[0] for s in siniflar if s[0]])

@app.get("/api/public/isimler")
def isimleri_getir(okul_adi: str, sinif: int):
    db = SessionLocal()
    ogrenciler = db.query(Ogrenci.id, Ogrenci.ad_soyad, Ogrenci.sube).filter(Ogrenci.okul == okul_adi, Ogrenci.sinif_seviyesi == sinif).order_by(Ogrenci.ad_soyad.asc()).all()
    db.close()
    return [{"id": o.id, "ad_soyad": o.ad_soyad, "sube": o.sube} for o in ogrenciler]

@app.get("/api/public/sonuc/{ogrenci_id}")
def sonuc_getir(ogrenci_id: int):
    db = SessionLocal()
    hedef = db.query(Ogrenci).filter(Ogrenci.id == ogrenci_id).first()
    if not hedef: raise HTTPException(status_code=404)
        
    if hedef.degerlendiren_ogretmen is None:
        db.close()
        return {
            "ad_soyad": hedef.ad_soyad, "okul": hedef.okul, "sinif": f"{hedef.sinif_seviyesi}/{hedef.sube}",
            "birinci_asama": hedef.birinci_asama_puani, "asil_puan": "-", "yedek_puan": "-", "sira": "-", "durum": "Değerlendirilmedi"
        }

    sinif_listesi = db.query(Ogrenci).filter(Ogrenci.sinif_seviyesi == hedef.sinif_seviyesi, Ogrenci.degerlendiren_ogretmen.isnot(None)).order_by(Ogrenci.asil_puan.desc(), Ogrenci.yedek_puan.desc(), Ogrenci.kura_degeri.desc()).all()
    db.close()

    sira = 0
    durum = "Net Asil Puan"
    for i, ogr in enumerate(sinif_listesi):
        if ogr.id == hedef.id:
            sira = i + 1
            esitlik_durumu = False
            kura_durumu = False
            if i > 0 and ogr.asil_puan == sinif_listesi[i-1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == sinif_listesi[i-1].yedek_puan: kura_durumu = True
            if i < len(sinif_listesi)-1 and ogr.asil_puan == sinif_listesi[i+1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == sinif_listesi[i+1].yedek_puan: kura_durumu = True
                
            if esitlik_durumu and not kura_durumu: durum = "Yedek Puanla Belirlendi"
            if kura_durumu: durum = "Otomatik Kurayla Belirlendi"
            break

    return {
        "ad_soyad": hedef.ad_soyad, "okul": hedef.okul, "sinif": f"{hedef.sinif_seviyesi}/{hedef.sube}",
        "birinci_asama": hedef.birinci_asama_puani, "asil_puan": hedef.asil_puan, 
        "yedek_puan": hedef.yedek_puan, "sira": sira, "durum": durum, "ilk_10": sira <= 10
    }
