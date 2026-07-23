---
name: external-search-cache-proxy
description: When integrating a quota-limited or paid external search/lookup API (YouTube Data API, Google Maps Places, OpenAI, third-party data providers) whose result includes an identifier you'll interpolate elsewhere (iframe src, redirect URL, a later DB query), wrap it in a server-side route that checks a cache table first, calls the external API only on a miss, validates the returned identifier against a strict format regex before using it anywhere, and writes through to the cache. Never call the API or expose its key from the client.
---

# External Search Cache Proxy

쿼터/비용이 있는 외부 검색·조회 API를 통합할 때, 클라이언트가 직접 호출하지 않게
서버 라우트로 감싸고, 캐시를 먼저 확인하고, 반환된 식별자를 다른 곳에 쓰기 전에
정규식으로 검증하세요.

## 인식 신호 (다음 중 하나라도 해당하면 적용)

- 통합하려는 API가 일일 쿼터나 호출당 비용이 있다 (YouTube Data API, Google
  Maps/Places, OpenAI, 유료 데이터 제공사 API 등).
- API 응답에 담긴 식별자(영상 ID, place ID, 토큰 등)를 **다른 곳에 그대로
  끼워 넣을** 계획이다 — iframe `src`, 리다이렉트 URL, 다음 DB 쿼리 등.
- 같은 검색어/조회 대상이 여러 사용자·세션에 걸쳐 반복될 가능성이 높다
  (같은 레시피명, 같은 장소명 등 — 캐시가 실제로 쓸모 있는 상황).
- 반대로, 쿼터 걱정이 없는 무료·무제한 API이거나 결과가 매번 달라 캐시가
  무의미하면 이 절차는 과잉이다 — 그냥 호출하면 된다.

## 절차

1. **캐시 테이블 설계**: 검색어(정규화된 쿼리 텍스트) → 결과 식별자로
   키를 잡는다.
2. **캐시 우선 조회**: 요청이 오면 캐시부터 확인한다. 히트하면 외부 API를
   호출하지 않고 즉시 반환한다.
3. **서버 사이드 전용 호출**: 캐시 미스일 때만 외부 API를 호출한다 —
   반드시 서버 라우트/API 엔드포인트에서만 호출하고, API 키가 클라이언트로
   절대 넘어가지 않게 한다.
4. **반환값 검증**: 그 API가 실제로 내놓는 식별자 형식에 맞는 엄격한
   정규식으로 검증한다 (예: YouTube 영상 ID는 정확히 11자,
   `[a-zA-Z0-9_-]`). 형식이 안 맞으면 신뢰하지 않고 null/에러 처리한다 —
   API 응답이라고 무조건 믿지 않는다. 특히 그 값이 iframe src나 다음 쿼리에
   그대로 들어간다면 이 검증 없이는 인젝션 통로가 된다.
5. **write-through 캐시**: 검증을 통과한 결과만 캐시에 저장한 뒤 클라이언트에
   반환한다.

## 구체적 사례

Fridge2Plate 프로젝트(`src/app/api/youtube/route.ts`)의 실제 구현:
레시피명으로 유튜브 영상을 찾는 라우트가 먼저 Supabase `youtube_cache`
테이블에서 같은 검색어의 `video_id`가 있는지 확인하고, 없으면 YouTube Data
API v3 `search` 엔드포인트를 서버에서만 호출한다. 응답에서 얻은 `videoId`를
`^[a-zA-Z0-9_-]{11}$` 정규식으로 검증한 뒤에만 Supabase에 upsert하고
클라이언트에 반환하며, 클라이언트 쪽 `YoutubeEmbed` 컴포넌트는 그 검증된
ID만 `<iframe src="https://www.youtube.com/embed/{videoId}">`에 넣어
렌더링한다. API 키는 서버 환경변수(`YOUTUBE_API_KEY`)에만 있고 클라이언트
번들에는 노출되지 않는다.

## 하지 않는 것

- 클라이언트에서 직접 외부 API를 호출하거나 API 키를 클라이언트 코드/번들에
  두지 않기
- API가 반환한 식별자를 검증 없이 iframe src나 DB 쿼리에 바로 끼워 넣지 않기
- 캐시 없이 매번 쿼터를 소모하며 같은 검색어를 반복 호출하지 않기
