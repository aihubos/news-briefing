# 뉴스 브리핑

국내 주요 신문·방송의 메인 헤드라인을 한 페이지로 모은 정적 브리핑입니다.

- 페이지: https://aihubos.github.io/news-briefing/
- 저장소: https://github.com/aihubos/news-briefing

매일 아침 8시(KST) 같은 형식·같은 저장소로 갱신합니다. 이 저장소의 `index.html`이 오늘 브리핑이고, 지난날은 `archive/YYYY-MM-DD.html`에 남습니다.

## 범위

종합일간지(조선·중앙·동아·한겨레·경향·한국일보·국민·서울신문·세계일보·문화일보), 경제지(매일경제·한국경제·서울경제·머니투데이), 통신·방송(연합뉴스, KBS, MBC, SBS, JTBC).

각 언론사 네이버 언론사 홈(`media.naver.com/press/{id}`)의 메인 뉴스 카드에서 상위 5건을 가져오고, 링크는 네이버 기사의 ‘기사 원문’(언론사 사이트)을 사용합니다. 가져오지 못한 언론사는 ‘수집 실패’로 표시합니다.

## 매일 재실행

작업 환경에서:

```bash
cd /workspace/news-briefing/site   # 또는 이 저장소를 클론한 경로
python3 scripts/build_briefing.py
# 생성물: index.html, archive/YYYY-MM-DD.html, data/YYYY-MM-DD.json

git add index.html archive data
git commit -m "briefing YYYY-MM-DD"
git push origin main
```

의존성: `python3`, `curl`, `beautifulsoup4`, `lxml`(없으면 스크립트가 설치를 시도합니다).

이미 모아 둔 JSON만으로 페이지를 다시 그릴 때:

```bash
python3 scripts/build_briefing.py --from-json data/YYYY-MM-DD.json
```

GitHub Pages는 `main` 브랜치 루트(`/`)를 사용합니다. `.nojekyll`이 포함되어 있습니다.
