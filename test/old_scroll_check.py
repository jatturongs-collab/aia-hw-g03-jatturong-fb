# Negative control: same code but with v2-style programmatic scrolling.
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'test')
import extract_posts as E
E.wheel_scroll = lambda page, dy: page.evaluate(f"window.scrollBy(0, {dy})")
E.wheel_nudge = lambda page: None
import runpy; sys.argv = ["mock_fb.py"] + sys.argv[1:]
runpy.run_path("test/mock_fb.py", run_name="__main__")
