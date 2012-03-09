import string
from itertools import chain

SET = string.letters + string.digits
DIGITS = string.digits
MODS = ['*', '?', '+']
SUCCESS = 'SUCCESS!'

class InvalidRegexError(Exception):
	pass

class CharacterClass(object):
	def __init__(self, characters=None, null=False, inf=False):
		self.characters = characters or []
		self.null = null
		self.inf = inf
		if self.inf: self.null = True

		if not isinstance(characters, list):
			self.characters = [characters]
		else:
			self.characters = characters

	def __repr__(self):
		if self.inf:
			mod = '*'
		elif self.null:
			mod = '?'
		else:
			mod = ''
		return '[' + ''.join(self.characters) + ']' + mod

	def match(self, character):
		return character in self.characters

	def default(self, character):
		return True

	def clone(self):
		return CharacterClass(characters=self.characters, null=self.null, inf=self.inf)

class DotClass(CharacterClass):
	def __init__(self, null=False, inf=False):
		super(DotClass, self).__init__(characters='.', null=null, inf=inf)

	def match(self, character):
		return True

	def clone(self):
		return DotClass(null=self.null, inf=self.inf)

class State(object):
	def __init__(self, links=None):
		self.links = links or []

	#def __repr__(self):
	#	out = []
	#	for fun, state, consume in self.links:
	#		target = 'self' if state is self else str(state) 
	#		s = str(fun.__self__) + '.' + fun.__name__  + ' '
	#		if consume: s += '!'
	#		s += '-> ' + target
	#		out.append(s)
	#	return ', '.join(out) 

	def link(self, fun, state, consume=True, throw_away=False):
		self.links.append((fun, state, consume, throw_away))

	def _try(self, link, consumed, remainder):
		fun, state, consume, throw_away = link
		if len(remainder):
			character = remainder[0]
			if consume:
				remainder = remainder[1:]
				if not throw_away:
					consumed += character
		else:
			if consume: return None
			character = ''

		if fun(character):
			return (state, consumed, remainder)
		else:
			return None
		
	def _exec(self, consumed, remainder):
		results = [self._try(link, consumed, remainder) for link in self.links]
		return filter(None, results)

	def run(self, seq, find_all):	
		success_states = [] 
		live_states = list(set(self._exec('', seq)))
		while True:
			if len(live_states) == 0:
				break
			links = []
			for result in live_states:
				if result[0] is SUCCESS: 
					success_states.append(result)
					if not find_all:
						break
				else:
					links.append(result)
			links = [state._exec(consumed, remainder) for state, consumed, remainder in links]
			live_states = list(set(chain(*links)))
		return success_states			

class Regex:
	def __init__(self, definition):
		self.definition = definition
		self._compile()

	def __repr__(self):
		return '/%s/' % self.definition

	def _compile(self):
		
		classes = []
		position = 0
		last_was_class = False

		#match [abc]
		match_character_class = State()
		match_open_class = State()
		match_inner_char = State()
		match_character_class.link(lambda c: c == '[', match_open_class)
		match_open_class.link(lambda c: c != ']', match_inner_char)
		match_inner_char.link(lambda c: c != ']', match_inner_char)
		match_inner_char.link(lambda c: c == ']', SUCCESS)

		def parse_character_class(s):
			classes.append(CharacterClass(list(s[1:-1])))
			last_was_class = True

		#match * or ? or +
		match_modifier = State()
		match_modifier.link(lambda c: c in MODS, SUCCESS)
        
		def parse_modifier(s):
			if not last_was_class: raise InvalidRegexException('modifier %s at %d has no class' % (s, position))
			c = classes[-1]
			if s == '?':
				c.null = True
			elif s == '*':
				c.inf = True
				c.null = True
			elif s == '+':
				#expand b+ to bb*
				new_class = c.clone()
				new_class.inf = True
				new_class.null = True
				classes.append(new_class)

		#match {3} or {12,16}
		match_range = State()
		match_open_range = State()
		match_range_character = State()
		match_comma = State()
		match_second_range_character = State()
		match_range.link(lambda c: c == '{', match_open_range)
		match_open_range.link(lambda c: len(c) == 1 and c in DIGITS, match_range_character)
		match_range_character.link(lambda c: len(c) == 1 and c in DIGITS, match_range_character)
		match_range_character.link(lambda c: c == '}', SUCCESS)
		match_range_character.link(lambda c: c == ',', match_comma)
		match_comma.link(lambda c: len(c) == 1 and c in DIGITS, match_second_range_character)
		match_second_range_character.link(lambda c: len(c) == 1 and c in DIGITS, match_second_range_character)
		match_second_range_character.link(lambda c: c == '}', SUCCESS)

		def parse_range(s):
			if not len(classes): raise InvalidRegexException('range %s at %d has no class' % (s, position))
			c = classes.pop()
			nums = s[1:-1].split(',')
			minimum = int(nums[0])

			for _ in range(minimum):
				classes.append(c.clone())

			if len(nums) > 1:
				maximum = int(nums[1])

				for _ in range(minimum, maximum):
					new_class = c.clone()
					new_class.null = True
					classes.append(new_class)

		#match \[ or \\
		match_escaped_char = State()
		match_slash = State()
		match_escaped_char.link(lambda c: c == '\\', match_slash)
		match_slash.link(lambda c: True, SUCCESS)
		
		def parse_escaped_char(s):
			classes.append(CharacterClass(s[1]))

		match_dot = State()
		match_dot.link(lambda c: c == '.', SUCCESS)
		
		def parse_dot(s):
			classes.append(DotClass())

		#match a or b
		match_character = State()
		match_character.link(lambda c: len(c) == 1 and c in SET, SUCCESS)

		def parse_character(s):
			classes.append(CharacterClass(s))

		tests = [ #test, parser, was_class
			(match_character_class, parse_character_class, True),
			(match_modifier, parse_modifier, False),
			(match_range, parse_range, False),
			(match_escaped_char, parse_escaped_char, True),
			(match_dot, parse_dot, True),
			(match_character, parse_character, True)
		]

		match_begin = False
		match_end = False

		definition = list(self.definition)

		if len(definition) and definition[0] == '^':
			match_begin = True
			definition = definition[1:]

		if len(definition) and definition[-1] == '$':
			match_end = True
			definition = definition[:-1]

		chunk = ''

		while len(definition) > 0:
			chunk += definition.pop(0)
			
			for test, parser, creates_class in tests:	
				if test.run(chunk, find_all=False):
					parser(chunk)
					chunk = ''
					last_was_class = creates_class
					break

		if len(chunk):
			raise InvalidRegexError("failed to parse %r" % chunk)

		#compile the character classes into a state machine
		next_state = self.initial_state = State()
		if not match_begin:
			self.initial_state.link(lambda c: True, self.initial_state, consume=True, throw_away=True)

		for i, c in enumerate(classes):
	
			state = next_state
			if i+1 == len(classes):
				if match_end:
					next_state = State()
					next_state.link(lambda c: c == '', SUCCESS, consume=False)
				else:
					next_state = SUCCESS
			else:
				next_state = State()

			if c.null:
				state.link(c.default, next_state, consume=False)
			if c.inf: #will always be null, because we expand b+ to bb*
				state.link(c.match, state, consume=True)
			else:
				state.link(c.match, next_state, consume=True)

	def match(self, s, greedy=True):
		results = self.initial_state.run(s, find_all=greedy)
		if results:
			if greedy:
				results = sorted(results, key=lambda r: len(r[1]))
				return results[-1][1]
			else:
				return results[0][1]
		else:
			return False

	def __call__(self, s):
		return self.match(s)


if __name__ == '__main__':
	def test_regex(definition, cases):
		r = Regex(definition)
		print 'testing', r
		for c, expected in cases:
			res = r.match(c)
			does_match = 'MATCH' if res != False else 'NO MATCH'
			print c.rjust(14) + ':', does_match.ljust(8), '(%s, %s)' % (expected, res), 'FAIL!!!' if res != expected else '' 

	test_regex('a', [('a', 'a'), ('b', False)])
	test_regex('abc', [('abc', 'abc'), ('xxabcxx', 'abc'), ('cab', False), ('aaa', False)])
	test_regex('ab?c', [('abc', 'abc'), ('ac', 'ac'), ('a', False), ('abbb', False), ('abbbc', False)])
	test_regex('ab*c', [('abc', 'abc'), ('ac', 'ac'), ('abbbbc', 'abbbbc'), ('abbb', False), ('accc', 'ac')])
	test_regex('ab+c', [('abc', 'abc'), ('abbbbc', 'abbbbc'), ('ac', False), ('ab', False)])
	test_regex('ab{3}c', [('abbbc', 'abbbc'), ('abc', False), ('ac', False)])
	test_regex('ab{1,3}c', [('abc', 'abc'), ('abbc', 'abbc'), ('abbbc', 'abbbc'), ('ac', False), ('abbbbc', False), ('abb', False)])
	test_regex('a[bc]*d', [('abcd', 'abcd'), ('ad', 'ad'), ('abcbcccccd', 'abcbcccccd'), ('addd', 'ad')])
	test_regex('.*', [('abhsueoah', 'abhsueoah'), ('blahblah', 'blahblah'), ('test[', 'test['), ('', '')])
	test_regex('aaa.*', [('aaahuetaot', 'aaahuetaot'), ('aaa', 'aaa'), ('blahbllah', False)])
	test_regex('a.*.*cc', [('aauoueoucc', 'aauoueoucc'), ('abcc', 'abcc'), ('acc', 'acc'), ('blahblah', False), ('xxcc', False)])
	test_regex('^abc', [('abc', 'abc'), ('abcdef', 'abc'), ('xxxabcxxx', False)])
	test_regex('abc$', [('abc', 'abc'), ('blahabc', 'abc'), ('abcblah', False)])
	test_regex('^abc$', [('abc', 'abc'), ('xxabc', False), ('abcxx', False)])
