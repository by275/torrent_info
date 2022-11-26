# torrent_info

libtorrent를 이용해 마그넷이나 토렌트 파일의 정보를 보여주는 SJVA 플러그인

## 요구조건

libtorrent가 설치가능한 모든 환경.

자동 설치는 아래 환경만 지원합니다.

- x86_64, aarch64, armv7l
- alpine docker

네이티브라면 직접 설치 후 설정 페이지에서 설치 여부를 확인할 수 있습니다.

## 준비과정

## 더 읽어보기

## Changelog

이후로는 [GITHUB commit](https://github.com/wiserain/torrent_info/commits/master)을 참고해 주세요.

v0.0.2.0

- libtorrent 설치 개선 (arm 지원)

v0.0.1.10 - libtorrent-1.2.6-200430.tar.gz

v0.0.1.8 - libtorrent-1.2.5-200314.tar.gz

v0.0.1.7

- api로 접근하던 UI 변경
- magnet2torrent 기능 삭제. 링크는 마그넷으로 대체
- json api 및 설명 추가 (설정/기타탭)

v0.0.1.6

- LOGIC: login_required / check_api 적용

v0.0.1.5

- LOGIC: size_fmt 추가
- WEBUI: size_fmt 윈도우의 [JEDEC 100B.01](https://superuser.com/a/938259) standard로 통일
- WEBUI: 설정 - 기타 탭 생성 및 정리

v0.0.1.2

- LOGIC: 메모리 대신 db 캐시를 사용하도록
- LOGIC: 캐시 사이즈 지정/변경 기능 제거
- LOGIC: 재시도 옵션 추가 (대기 시간을 짧게 재시도 횟수를 늘려서 튜닝)
- LOGIC: magnet2torrent 기능 잠정 중단

v0.0.1.1 - libtorrent-1.2.4-200211.tar.gz

v0.0.1.0

- SJVA0.2: 웹 연동 대응

v0.0.0.9

- LOGIC: 코드 정리, 소소한 수정
- WEBUI: magnet uri text-truncate

v0.0.0.8

- LOGIC: 캐시 임시 수정

v0.0.0.7 - libtorrent-1.2.3-191227.tar.gz

- alpine3.10
- python2.7.17
- libboost1.71
- libtorrent1.2.3

v0.0.0.6

- WEBUI: 마그넷 + 토렌트 파일 하나로 통합
- LOGIC: 사용자 트래커 기능
- LOGIC: 시간 데이터 로컬 기준으로 통일

v0.0.0.5

- WEBUI: 결과를 json 대신 좀 더 보기 좋은 포맷으로
- WEBUI: 항목 클릭해서 복사
- WEBUI: magnet:?xt=urn:btih:로 시작안하는 마그넷은 인포해쉬로 간주

v0.0.0.4

- LOGIC: 자체 캐시를 좀 더 적극적으로 활용, 웹에서 검색시 등...

## TODO

- [ ] LOGIC: flask_restful 이용해서 api 정리 (sjva에서 설치가 제거된 것 같음)
- [x] LOGIC: --no-cache 옵션
- [x] WEBUI: cosmetic issue, button align, responsive view
- [x] LOGIC: proxy 적용
- [ ] LOGIC: 해쉬로 된 파일명 변경 기능
- [x] WEBUI: load more
- [ ] LOGIC: 트래커 챌린지
- [ ] LOGIC: 설치 프로세스에 api 적용
- [x] LOGIC: retry 옵션
- [x] LOGIC: 메모리 캐시에서 db를 이용하는 것은 잠시 보류
