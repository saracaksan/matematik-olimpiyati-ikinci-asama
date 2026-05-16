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
# 1. VERİTABANI BAĞLANTISI VE MODELLER
# ==========================================
DATABASE_URL = "sqlite:///./olimpiyat.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# YÖNETİCİ ŞİFRESİ (Sabit)
YONETICI_SIFRE = "Sarac.47"

class SistemAyar(Base):
    __tablename__ = "sistem_ayarlari"
    ayar_adi = Column(String, primary_key=True, index=True)
    ayar_degeri = Column(Boolean, default=False)

class Ogretmen(Base):
    __tablename__ = "ogretmenler"
    id = Column(Integer, primary_key=True, index=True)
    ad_soyad = Column(String)
    kullanici_adi = Column(String, unique=True, index=True)
    sifre = Column(String)

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
    yedek_aktif_mi = Column(Boolean, default=False) 
    
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

# ==========================================
# 2. PYDANTIC ŞEMALARI (VERİ DOĞRULAMA)
# ==========================================
class LoginRequest(BaseModel):
    kullanici_adi: str
    sifre: str

class YeniOgretmenRequest(BaseModel):
    sifre: str
    ad_soyad: str
    kullanici_adi: str
    ogretmen_sifre: str

class YeniOgrenciRequest(BaseModel):
    sifre: str
    ad_soyad: str
    okul: str
    sinif: int
    sube: str
    birinci_asama_puani: Optional[float] = None
    zorla_kaydet: bool = False

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

class YedekAktiflestirRequest(BaseModel):
    sifre: str
    ogrenci_idler: List[int]

# ==========================================
# FASTAPI BAŞLATMA VE CEVAP ANAHTARININ YÜKLENMESİ
# ==========================================
app = FastAPI(title="MEB 1. Matematik Olimpiyatı Arka Plan Sistemi")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
Base.metadata.create_all(bind=engine)

@app.on_event("startup")
def baslangic_verilerini_yukle():
    db = SessionLocal()
    if db.query(SistemAyar).filter(SistemAyar.ayar_adi == "sistem_kilitli").first() is None:
        db.add(SistemAyar(ayar_adi="sistem_kilitli", ayar_degeri=False))
    
    # Sisteme Gömülü Otomatik Cevap Anahtarı
    CEVAP_ANAHTARI = {
        "asil": {
            4: ["15", "$\\frac{7}{10}$", "10:10", "300", "140", "20", "11:00", "110", "3840", "300"],
            5: ["2", "24", "105", "55", "70", "900", "3600", "112", "30", "19"],
            6: ["10", "349,20", "36", "131", "40", "2", "22", "70", "132", "70"],
            7: ["-7", "9", "8x-20", "340", "12", "60", "135", "6000", "30", "24"],
            9: ["19", "228", "40", "84", "330", "72", "3", "35", "36", "145"],
            10: ["30", "180", "7,5", "7", "360", "74", "2", "$24\\sqrt{3}$", "45", "25"]
        },
        "yedek": {
            4: ["400", "80", "148", "Ay", "20"],
            5: ["1245", "450", "96", "150", "800"],
            6: ["9", "180", "22", "20", "110"],
            7: ["400", "15", "150", "12500", "%8 artar"],
            9: ["20", "33", "13", "645", "9"],
            10: ["105", "12", "6", "12", "196"]
        }
    }

    siniflar = [4, 5, 6, 7, 8, 9, 10, 11, 12]
    if db.query(Soru).first() is None:
        for s in siniflar:
            # Asil Sorular (10 Soru) - Puanlar: İlk 4 soru 3 Puan, 5-7. sorular 4 Puan, 8-10. sorular 5 Puan
            for i in range(1, 11):
                puan = 3.0 if i <= 4 else (4.0 if i <= 7 else 5.0)
                cevap = ""
                if s in CEVAP_ANAHTARI["asil"] and i <= len(CEVAP_ANAHTARI["asil"][s]):
                    cevap = CEVAP_ANAHTARI["asil"][s][i-1]
                db.add(Soru(sinif_seviyesi=s, soru_tipi="asil", soru_no=i, puan_degeri=puan, dogru_cevap_metni=cevap))
            
            # Yedek Sorular (5 Soru) - Puanlar: İlk 2 soru 4 Puan, 3-5. sorular 5 Puan
            for i in range(1, 6):
                puan = 4.0 if i <= 2 else 5.0
                cevap = ""
                if s in CEVAP_ANAHTARI["yedek"] and i <= len(CEVAP_ANAHTARI["yedek"][s]):
                    cevap = CEVAP_ANAHTARI["yedek"][s][i-1]
                db.add(Soru(sinif_seviyesi=s, soru_tipi="yedek", soru_no=i, puan_degeri=puan, dogru_cevap_metni=cevap))
    db.commit()
    db.close()

# ==========================================
# GİRİŞ, KİLİT VE ÖĞRETMEN YÖNETİMİ
# ==========================================
@app.post("/api/login")
def sisteme_giris(req: LoginRequest):
    if req.kullanici_adi == "admin" and req.sifre == YONETICI_SIFRE:
        return {"rol": "yonetici"}
    
    db = SessionLocal()
    ogretmen = db.query(Ogretmen).filter(Ogretmen.kullanici_adi == req.kullanici_adi, Ogretmen.sifre == req.sifre).first()
    db.close()
    
    if ogretmen:
        return {"rol": "ogretmen", "ogretmen_adi": ogretmen.ad_soyad}
    raise HTTPException(status_code=401, detail="Kullanıcı adı veya şifre hatalı!")

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
    return {"mesaj": "Sistem başarıyla güncellendi."}

@app.post("/api/yonetici/ogretmen_ekle")
def ogretmen_ekle(req: YeniOgretmenRequest):
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    mevcut = db.query(Ogretmen).filter(Ogretmen.kullanici_adi == req.kullanici_adi).first()
    if mevcut:
        db.close()
        raise HTTPException(status_code=400, detail="Bu kullanıcı adı zaten alınmış!")
    db.add(Ogretmen(ad_soyad=req.ad_soyad, kullanici_adi=req.kullanici_adi, sifre=req.ogretmen_sifre))
    db.commit()
    db.close()
    return {"mesaj": "Öğretmen hesabı başarıyla oluşturuldu."}

@app.get("/api/yonetici/ogretmenler")
def ogretmen_listesi(sifre: str):
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogretmenler = db.query(Ogretmen).all()
    db.close()
    return ogretmenler

@app.delete("/api/yonetici/ogretmen_sil/{id}")
def ogretmen_sil(id: int, sifre: str):
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogretmen = db.query(Ogretmen).filter(Ogretmen.id == id).first()
    if ogretmen:
        db.delete(ogretmen)
        db.commit()
    db.close()
    return {"mesaj": "Öğretmen hesabı silindi."}

# ==========================================
# YÖNETİCİ: ÖĞRENCİ YÖNETİMİ & EŞİTLİK TESPİTİ
# ==========================================
@app.get("/api/yonetici/esitlik_raporu")
def esitlik_raporu(sifre: str):
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogrenciler = db.query(Ogrenci).filter(Ogrenci.degerlendiren_ogretmen.isnot(None)).all()
    db.close()
    
    esitlikler = {}
    for ogr in ogrenciler:
        anahtar = f"{ogr.sinif_seviyesi}_sinif_{ogr.asil_puan}_puan"
        if anahtar not in esitlikler: esitlikler[anahtar] = []
        esitlikler[anahtar].append(ogr)
        
    rapor = []
    for anahtar, ogr_list in esitlikler.items():
        if len(ogr_list) > 1: 
            ogrenci_verileri = []
            yedek_zaten_aktif_mi = True
            for o in ogr_list:
                if not o.yedek_aktif_mi: yedek_zaten_aktif_mi = False
                ogrenci_verileri.append({"id": o.id, "ad_soyad": o.ad_soyad, "okul": o.okul, "sube": o.sube, "yedek_aktif_mi": o.yedek_aktif_mi})
                
            sinif = anahtar.split('_')[0]
            puan = anahtar.split('_')[2]
            rapor.append({
                "sinif": sinif,
                "asil_puan": puan,
                "ogrenciler": ogrenci_verileri,
                "tumu_aktif_mi": yedek_zaten_aktif_mi
            })
    return rapor

@app.post("/api/yonetici/yedek_aktiflestir")
def yedek_aktiflestir(req: YedekAktiflestirRequest):
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    db.query(Ogrenci).filter(Ogrenci.id.in_(req.ogrenci_idler)).update({"yedek_aktif_mi": True}, synchronize_session=False)
    db.commit()
    db.close()
    return {"mesaj": "Seçili öğrenciler için Eşitlik Bozma (Yedek) Sınavı aktifleştirildi."}

@app.post("/api/yonetici/ogrenci_ekle")
def ogrenci_ekle_manuel(req: YeniOgrenciRequest):
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
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
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogrenciler = db.query(Ogrenci).order_by(Ogrenci.sinif_seviyesi.asc(), Ogrenci.ad_soyad.asc()).all()
    db.close()
    return ogrenciler

@app.delete("/api/yonetici/ogrenci_sil/{ogrenci_id}")
def yonetici_ogrenci_sil(ogrenci_id: int, sifre: str):
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogrenci = db.query(Ogrenci).filter(Ogrenci.id == ogrenci_id).first()
    db.delete(ogrenci)
    db.commit()
    db.close()
    return {"mesaj": "Öğrenci sistemden TAMAMEN SİLİNDİ."}

@app.put("/api/yonetici/ogrenci_guncelle/{ogrenci_id}")
def yonetici_ogrenci_bilgi_guncelle(ogrenci_id: int, req: OgrenciGuncelleRequest):
    if req.sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    ogrenci = db.query(Ogrenci).filter(Ogrenci.id == ogrenci_id).first()
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
                mevcut = db.query(Ogrenci).filter(Ogrenci.ad_soyad == ad_soyad, Ogrenci.sinif_seviyesi == sinif).first()
                if mevcut:
                    atlanan += 1
                    continue
                db.add(Ogrenci(okul=okul, ad_soyad=ad_soyad, sinif_seviyesi=sinif, sube=sube, ogrenci_no=ogrenci_no, birinci_asama_puani=birinci_asama))
                eklenen += 1
    db.commit()
    db.close()
    return {"mesaj": f"{eklenen} yeni öğrenci eklendi. (Mevcut {atlanan} kişi atlandı.)"}

# ==========================================
# YÖNETİCİ: RAPORLAMA VE SORULAR
# ==========================================
@app.get("/api/yonetici/detayli_rapor")
def yonetici_detayli_rapor(sifre: str):
    if sifre != YONETICI_SIFRE: raise HTTPException(status_code=401)
    db = SessionLocal()
    siniflar = db.query(Ogrenci.sinif_seviyesi).distinct().order_by(Ogrenci.sinif_seviyesi).all()
    siniflar = [s[0] for s in siniflar if s[0]]
    
    rapor = {}
    for sinif in siniflar:
        ogrenciler = db.query(Ogrenci).filter(Ogrenci.sinif_seviyesi == sinif, Ogrenci.degerlendiren_ogretmen.isnot(None)).order_by(Ogrenci.asil_puan.desc(), Ogrenci.yedek_puan.desc(), Ogrenci.kura_degeri.desc()).all()
        sinif_sonuclari = []
        for i, ogr in enumerate(ogrenciler):
            esitlik_durumu, kura_durumu = False, False
            if i > 0 and ogr.asil_puan == ogrenciler[i-1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == ogrenciler[i-1].yedek_puan: kura_durumu = True
            if i < len(ogrenciler)-1 and ogr.asil_puan == ogrenciler[i+1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == ogrenciler[i+1].yedek_puan: kura_durumu = True
                
            durum_metni = "Net Asil Puan"
            if esitlik_durumu and not kura_durumu: durum_metni = "Yedek Puan İle Belirlendi"
            if kura_durumu: durum_metni = "Otomatik Kurayla Belirlendi"
            if ogr.yedek_aktif_mi and ogr.yedek_puan == 0: durum_metni = "Yedek Sınav Bekliyor"
                
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

# ==========================================
# ÖĞRETMEN: GEÇMİŞ HAFIZA, YEDEK LİSTESİ VE DEĞERLENDİRME
# ==========================================
@app.get("/api/ogretmen/panolar")
def ogretmen_panolari(ogretmen_ad: str):
    db = SessionLocal()
    gecmis = db.query(Ogrenci).filter(Ogrenci.degerlendiren_ogretmen == ogretmen_ad).all()
    yedek_bekleyen = db.query(Ogrenci).filter(Ogrenci.degerlendiren_ogretmen == ogretmen_ad, Ogrenci.yedek_aktif_mi == True).all()
    db.close()
    
    gecmis_liste = [{"id": o.id, "ad_soyad": o.ad_soyad, "sinif": o.sinif_seviyesi, "asil": o.asil_puan, "yedek": o.yedek_puan} for o in gecmis]
    yedek_liste = [{"id": o.id, "ad_soyad": o.ad_soyad, "sinif": o.sinif_seviyesi} for o in yedek_bekleyen]
    return {"gecmis_okunanlar": gecmis_liste, "yedek_bekleyenler": yedek_liste}

@app.get("/api/ogretmen/ogrenci_durumu/{ogrenci_id}")
def ogrenci_durumu(ogrenci_id: int):
    db = SessionLocal()
    ogr = db.query(Ogrenci).filter(Ogrenci.id == ogrenci_id).first()
    if not ogr: raise HTTPException(status_code=404)
    
    yanitlar = db.query(Yanit).filter(Yanit.ogrenci_id == ogrenci_id).all()
    eski_yanitlar = {y.soru_id: y.dogru_mu for y in yanitlar}
    db.close()
    return {
        "yedek_aktif_mi": ogr.yedek_aktif_mi,
        "eski_yanitlar": eski_yanitlar,
        "okuyan_ogretmen": ogr.degerlendiren_ogretmen
    }

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
        raise HTTPException(status_code=403, detail=f"Bu kağıt daha önce {ogrenci.degerlendiren_ogretmen} tarafından okunmuş!")

    for yanit in req.yanitlar:
        soru = db.query(Soru).filter(Soru.id == yanit.soru_id).first()
        mevcut_yanit = db.query(Yanit).filter(Yanit.ogrenci_id == ogrenci.id, Yanit.soru_id == soru.id).first()
        if mevcut_yanit: mevcut_yanit.dogru_mu = yanit.dogru_mu
        else: db.add(Yanit(ogrenci_id=ogrenci.id, soru_id=soru.id, dogru_mu=yanit.dogru_mu))
    db.commit()

    asil_toplam, yedek_toplam = 0.0, 0.0
    tum_yanitlar = db.query(Yanit).filter(Yanit.ogrenci_id == ogrenci.id).all()
    for y in tum_yanitlar:
        if y.dogru_mu:
            if y.soru.soru_tipi == "asil": asil_toplam += y.soru.puan_degeri
            elif y.soru.soru_tipi == "yedek": yedek_toplam += y.soru.puan_degeri

    ogrenci.asil_puan = asil_toplam
    ogrenci.yedek_puan = yedek_toplam
    ogrenci.degerlendiren_ogretmen = req.ogretmen_ad_soyad
    db.commit()
    db.close()
    return {"mesaj": "Değerlendirme Başarıyla Kaydedildi!"}

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
# PUBLIC UÇLAR (SORGULAMA VE SORULAR)
# ==========================================
@app.get("/api/sorular/{sinif_seviyesi}")
def sorulari_getir(sinif_seviyesi: int):
    db = SessionLocal()
    sorular = db.query(Soru).filter(Soru.sinif_seviyesi == sinif_seviyesi).order_by(Soru.soru_tipi.asc(), Soru.soru_no.asc()).all()
    db.close()
    return sorular

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
        return {"ad_soyad": hedef.ad_soyad, "okul": hedef.okul, "sinif": f"{hedef.sinif_seviyesi}/{hedef.sube}", "birinci_asama": hedef.birinci_asama_puani, "asil_puan": "-", "yedek_puan": "-", "sira": "-", "durum": "Değerlendirilmedi"}

    sinif_listesi = db.query(Ogrenci).filter(Ogrenci.sinif_seviyesi == hedef.sinif_seviyesi, Ogrenci.degerlendiren_ogretmen.isnot(None)).order_by(Ogrenci.asil_puan.desc(), Ogrenci.yedek_puan.desc(), Ogrenci.kura_degeri.desc()).all()
    db.close()

    sira = 0
    durum = "Asil Puanla Belirlendi"
    for i, ogr in enumerate(sinif_listesi):
        if ogr.id == hedef.id:
            sira = i + 1
            esitlik_durumu, kura_durumu = False, False
            if i > 0 and ogr.asil_puan == sinif_listesi[i-1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == sinif_listesi[i-1].yedek_puan: kura_durumu = True
            if i < len(sinif_listesi)-1 and ogr.asil_puan == sinif_listesi[i+1].asil_puan:
                esitlik_durumu = True
                if ogr.yedek_puan == sinif_listesi[i+1].yedek_puan: kura_durumu = True
                
            if esitlik_durumu and not kura_durumu: durum = "Yedek Puanla Belirlendi"
            if kura_durumu: durum = "Otomatik Kurayla Belirlendi"
            if hedef.yedek_aktif_mi and hedef.yedek_puan == 0: durum = "Yedek Sınav Sonucu Bekleniyor"
            break

    return {
        "ad_soyad": hedef.ad_soyad, "okul": hedef.okul, "sinif": f"{hedef.sinif_seviyesi}/{hedef.sube}",
        "birinci_asama": hedef.birinci_asama_puani, "asil_puan": hedef.asil_puan, 
        "yedek_puan": hedef.yedek_puan, "sira": sira, "durum": durum, "ilk_10": sira <= 10
    }
