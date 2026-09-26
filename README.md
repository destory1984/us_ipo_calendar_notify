# 미국 IPO 목록

미국에서 곧 상장할 종목을 나스닥 IPO 캘린더에서 가져와 보여 주고, 원하면 텔레그램으로 보낸다.
파이썬 기본 라이브러리만 쓰고, API 키는 필요 없다.

## 쓰는 법

```
python ipo_fetch.py                  # 상장 예정 (날짜가 잡힌 것만)
python ipo_fetch.py -s filed         # 이번 달 상장 신청 건 (날짜 없는 후보)
python ipo_fetch.py --no-spac        # SPAC 빼기
python ipo_fetch.py --csv ipo.csv    # CSV로 저장
python ipo_fetch.py --telegram       # 텔레그램으로도 보내기
```

`-s` 로 고를 수 있는 구역: `priced`(상장 완료), `upcoming`(상장 예정), `filed`(신청 접수), `withdrawn`(철회).
지난 달 것까지 보려면 `-m 3` 처럼 달 수를 준다.

나오는 열: 날짜, 구역, 종목 코드, 공모가, 공모 규모, 회사 이름, 업종.

## 데이터는 어디서 오나

- 목록: 나스닥 IPO 캘린더가 쓰는 `api.nasdaq.com/api/ipo/calendar`. 나스닥 캘린더지만 NYSE 상장 건도 들어 있다.
  공식 API가 아니라서 나스닥이 형식을 바꾸면 멈출 수 있다.
- 업종: 나스닥 상세에서 회사의 SEC 번호(CIK)를 얻고, SEC EDGAR에 등록된 업종 코드(SIC)를 읽어 한글로 바꾼다.
  한글 이름 표는 `sic_ko.py` 에 있다. SIC는 거친 분류라 실제 사업과 다를 수 있다. 예를 들어 스마트 반지 회사가 "전자 기기"로 나온다.
  종목마다 요청이 두 번씩 나가므로 목록이 길면 느리다. `--no-industry` 로 건너뛸 수 있다.

날짜가 잡혀 올라오는 것은 보통 상장 1~2주 전부터다. 그보다 먼 후보는 `-s filed` 로 본다.

## 텔레그램

토큰과 대화방 번호는 코드에 넣지 않고 환경변수로 준다.

```
setx TELEGRAM_BOT_TOKEN "봇 토큰"
setx TELEGRAM_CHAT_ID   "대화방 번호"
```

`setx` 로 넣은 뒤에는 새 창을 열어야 적용된다.

## 매주 자동으로 보내기 (윈도우 작업 스케줄러)

PowerShell에서 한 번 등록한다. 아래는 매주 일요일 오후 2시에 보내는 예다.

```powershell
$py = python -c "import sys; print(sys.executable)"
$a = New-ScheduledTaskAction -Execute $py -Argument '"C:\경로\ipo_fetch.py" --telegram' -WorkingDirectory 'C:\경로'
$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 14:00
$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
Register-ScheduledTask -TaskName 'IPO 주간 텔레그램' -Action $a -Trigger $t -Settings $s
```

`-StartWhenAvailable` 을 넣으면 그 시각에 PC가 꺼져 있었어도 켜진 뒤 한 번 돈다.
지우려면 `Unregister-ScheduledTask -TaskName 'IPO 주간 텔레그램'`.
