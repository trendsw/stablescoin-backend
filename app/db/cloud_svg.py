from dataclasses import dataclass
from typing import Optional
import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
import base64

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)


@dataclass
class CertificateData:
    post_id: str
    title: str
    description: str
    poster_wallet: str
    timestamp: str
    tx_hash: Optional[str] = None

    
def generate_certificate_svg(data: CertificateData) -> str:
    title = data.title[:50] + "..." if len(data.title) > 50 else data.title
    description = data.description[:60] + "..." if len(data.description) > 60 else data.description
    wallet = f"{data.poster_wallet[:20]}...{data.poster_wallet[-10:]}"
    
    tx_html = ""
    if data.tx_hash:
        tx_html = f"""
        <text x="400" y="860" text-anchor="middle" class="timestamp-text">
          TX: {data.tx_hash[:20]}...{data.tx_hash[-10:]}
        </text>
        """

    return f"""
<svg width="800" height="1000" viewBox="0 0 800 1000"
     xmlns="http://www.w3.org/2000/svg">

  <defs>
    <style>
      .certificate-bg {{ fill: #f8fafc; stroke: #e2e8f0; stroke-width: 4; }}
      .header-text {{ font-family: Arial, sans-serif; font-size: 48px; font-weight: bold; fill: #1e293b; }}
      .sub-text {{ font-family: Arial, sans-serif; font-size: 24px; fill: #64748b; }}
      .title-text {{ font-family: Arial, sans-serif; font-size: 36px; font-weight: bold; fill: #b45309; font-style: italic; }}
      .content-text {{ font-family: Arial, sans-serif; font-size: 18px; fill: #374151; }}
      .timestamp-text {{ font-family: Arial, sans-serif; font-size: 16px; fill: #6b7280; }}
      .decorative-border {{ fill: none; stroke: #d1d5db; stroke-width: 2; stroke-dasharray: 10,5; }}
    </style>

    <pattern id="cornerPattern" width="40" height="40" patternUnits="userSpaceOnUse">
      <path d="M0,20 Q20,0 40,20 Q20,40 0,20" fill="#e5e7eb" opacity="0.3"/>
    </pattern>
  </defs>

  <rect x="20" y="20" width="760" height="960" rx="15" class="certificate-bg"/>
  <rect x="0" y="0" width="80" height="80" fill="url(#cornerPattern)"/>
  <rect x="720" y="0" width="80" height="80" fill="url(#cornerPattern)"/>
  <rect x="0" y="920" width="80" height="80" fill="url(#cornerPattern)"/>
  <rect x="720" y="920" width="80" height="80" fill="url(#cornerPattern)"/>

  <circle cx="400" cy="120" r="40" fill="#374151"/>
  <path d="M380,105 L400,125 L420,105" stroke="#fff" stroke-width="3" fill="none"/>

  <text x="400" y="220" text-anchor="middle" class="header-text">CERTIFICATE</text>
  <text x="400" y="270" text-anchor="middle" class="sub-text">for the</text>
  <text x="400" y="340" text-anchor="middle" class="title-text">Digital Content</text>

  <text x="400" y="420" text-anchor="middle" class="content-text">Blockchain Verification</text>

  <text x="100" y="550" class="content-text">
    This certificate validates the authenticity and ownership of the digital content.
  </text>

  <text x="100" y="720" class="content-text">Title: {title}</text>
  <text x="100" y="750" class="content-text">Description: {description}</text>
  <text x="100" y="780" class="content-text">Owner: {wallet}</text>

  <text x="400" y="830" text-anchor="middle" class="timestamp-text">{data.timestamp}</text>
  {tx_html}

  <rect x="40" y="40" width="720" height="920" rx="10" class="decorative-border"/>

  <circle cx="400" cy="980" r="15" fill="#f59e0b"/>
  <text x="400" y="987" text-anchor="middle"
        style="font-family: Arial; font-size: 16px; font-weight: bold; fill: white;">₿</text>

</svg>
""".strip()


def upload_certificate_svg(svg: str, public_id: str) -> str:
    svg_base64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
    data_uri = f"data:image/svg+xml;base64,{svg_base64}"

    result = cloudinary.uploader.upload(
        data_uri,
        resource_type="image",
        public_id=public_id,
        folder="uhalisi_posts",
        overwrite=True,
        format="svg"
    )

    return result["secure_url"]