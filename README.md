this is a simple implementation of regex done in python for my own education. usage:


	>>> from pyregex import Regex
	>>> r = Regex('^abc{2,3}[ed]+')
	>>> r.match('something random')
	False
	>>> r.match('abccdedededexxx')
	'abcdededede'
	>>> r.match('abccdedededexxx', greedy=False)
	'abccd'


or, to run the tests, just run `python pyregex.py`
