# Kocom Wallpad

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

코콤 월패드를 홈 어시스턴트에서 사용할 수 있도록 하는 통합구성요소입니다.

> [!WARNING]
> 이 통합구성요소는 소켓(EW11) 연결방식만 지원합니다.

## 설치 방법

1. 홈 어시스턴트 설정 폴더(configuration.yaml이 있는 폴더)로 이동합니다.
1. 만약 `custom_components` 폴더가 없다면 생성합니다.
1. `custom_components` 폴더 안에 `kocom_wallpad` 폴더를 생성합니다.
1. 다운로드한 파일을 생성한 폴더에 복사합니다.
1. 홈 어시스턴트를 재시작합니다.
1. 홈 어시스턴트 설정 페이지에서 "기기 및 서비스" -> "통합구성요소" -> "+ 통합구성요소 추가하기" 버튼을 눌러 "kocom wallpad"를 검색하여 설치합니다.

## 기능

- 조명
    - on / off
- 난방
    - on / off / away
    - 목표 온도 설정 / 현재 온도 표시
- 가스밸브
    - 닫기
- 환기(전열교환기)
    - on / off
    - 3단계 조절


## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md)


[commits-shield]: https://img.shields.io/github/commit-activity/y/zmtq05/kocom_wallpad.svg?style=for-the-badge
[commits]: https://github.com/zmtq05/kocom_wallpad/commits/main
[license-shield]: https://img.shields.io/github/license/zmtq05/kocom_wallpad.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/zmtq05/kocom_wallpad.svg?style=for-the-badge
[releases]: https://github.com/zmtq05/kocom_wallpad/releases
