let s:spinner_timer = -1
let s:spinner_index = 0
let s:spinner_text = ''
let s:spinner_chars = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'] " nice unicode spinner

function! s:SpinnerTick(timer) abort
  let s:spinner_index = (s:spinner_index + 1) % len(s:spinner_chars)
  echo s:spinner_text . ' ' . s:spinner_chars[s:spinner_index]
  redraw
endfunction

function! ollama#spinner#SpinnerStart(msg) abort
  if s:spinner_timer != -1
    call s:SpinnerStop()
  endif
  let s:spinner_text = a:msg
  let s:spinner_index = 0
  let s:spinner_timer = timer_start(100, function('s:SpinnerTick'), {'repeat': -1})
endfunction

function! ollama#spinner#SpinnerStop(status) abort
  if s:spinner_timer != -1
    call timer_stop(s:spinner_timer)
    let s:spinner_timer = -1
  endif
  if a:status == 0
      echo s:spinner_text . ' ✅'
  else
      echo s:spinner_text . ' ❌'
  endif
  redraw
endfunction

