data = open('games/templates/games/student/leaderboard.html', 'rb').read()
pos = 7088
line_num = data[:pos].count(b'\n') + 1
line_start = data.rfind(b'\n', 0, pos) + 1
line_end = data.find(b'\n', pos)
print(f'Line {line_num}, byte at pos: {hex(data[pos])}')
ctx = data[max(0, line_start - 50):line_end + 50].decode('utf-8', errors='replace')
print('Context:')
print(ctx)
