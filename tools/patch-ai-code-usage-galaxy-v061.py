from pathlib import Path
import re

root=Path('/tmp/src/src/android')
main=root/'app/src/main/java/com/myvision/codexusage/MainActivity.java'
claude=root/'app/src/main/java/com/myvision/codexusage/ClaudeSyncApi.java'
strings=root/'app/src/main/res/values/strings.xml'
build=root/'app/build.gradle.kts'

s=main.read_text(encoding='utf-8')
s=s.replace('Claude Code v2.1 계열의 공식 statusLine JSON에서 rate_limits.five_hour / seven_day 값을 데스크톱 앱이 수집합니다. Claude Code에서 첫 API 응답이 나온 뒤부터 값이 생깁니다.\\n\\n상단 배지의 CX/CL 숫자는 ‘남은 비율’을 뜻합니다.',
'''Claude는 Mac/Windows AI Code Usage v0.6.x가 기존 Claude Code OAuth 로그인으로 직접 조회한 5시간/7일 사용량 숫자만 휴대폰으로 전달합니다. Claude 로그인 토큰은 Galaxy로 전송되지 않습니다.\\n\\nCodex는 Galaxy에서 직접 로그인·조회합니다. 상단 배지의 CX/CL 숫자는 ‘남은 비율’을 뜻합니다.''')
s=s.replace('Mac/Windows AI Code Usage 앱에서 ‘휴대폰 연결 주소 복사’를 누른 뒤 아래에 한 번 붙여넣으세요. Claude 로그인 토큰은 휴대폰으로 전송되지 않습니다.',
'''Mac/Windows AI Code Usage v0.6.x에서 ‘휴대폰 연결 주소 복사’를 누른 뒤 아래에 한 번 붙여넣으세요. Claude는 데스크톱에서 조회한 숫자만 동기화하고 로그인 토큰은 휴대폰으로 보내지 않습니다.''')
s=s.replace('데스크톱 연결 필요','Mac/Windows 연결 필요')
main.write_text(s,encoding='utf-8')

c=claude.read_text(encoding='utf-8')
c=c.replace('데스크톱에 Claude 사용량이 아직 없습니다. Claude Code에서 메시지를 한 번 보내세요.',
            '데스크톱에 Claude 사용량이 아직 없습니다. Mac/Windows AI Code Usage에서 Claude 사용량을 한 번 새로고침하세요.')
claude.write_text(c,encoding='utf-8')

x=strings.read_text(encoding='utf-8')
x=x.replace('Codex 주간 및 5시간 사용량 위젯','Codex·Claude Code 5시간 및 7일 사용량 위젯')
strings.write_text(x,encoding='utf-8')

b=build.read_text(encoding='utf-8')
# Update any existing Android version values without depending on the old exact number.
b=re.sub(r'versionCode\s*=\s*\d+', 'versionCode = 61', b)
b=re.sub(r'versionName\s*=\s*"[^"]+"', 'versionName = "0.6.1"', b)
build.write_text(b,encoding='utf-8')

print('Galaxy v0.6.1 patch applied')
