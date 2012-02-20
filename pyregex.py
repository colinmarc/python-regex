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

	def __repr__(self):
		out = []
		for fun, state, consume in self.links:
			target = 'self' if state is self else str(state) 
			s = str(fun.__self__) + '.' + fun.__name__  + ' '
			if consume: s += '!'
			s += '-> ' + target
			out.append(s)
		return ', '.join(out) 

	def link(self, fun, state, consume=True):
		self.links.append((fun, state, consume))

	def __try(self, link, s):
		fun, state, consume = link
		s = list(s)
		if len(s):
			character = s.pop(0) if consume else s[0]
		else:
			if consume: return []
			character = ''

		#if hasattr(fun, '__self__'): print 'trying', str(fun.__self__) + '.' + fun.__name__, character, '...', fun(character), ' -> ', state
		if fun(character):
			return [state] if not isinstance(state, State) else state.__exec(s)
		else:
			return []
		
	def __exec(self, s):
		return list(set(filter(None, chain(*[self.__try(link, s) for link in self.links]))))

	def start(self, s):
		return self.__exec(s)
		
class Regex:
	def __init__(self, definition):
		self.definition = definition
		self.__compile()

	def __repr__(self):
		return 'Regex(%s)' % self.definition

	def __compile(self):
		
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

		def run_test(test, s):
			return SUCCESS in test.start(s)

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
				if run_test(test, chunk):
					parser(chunk)
					chunk = ''
					last_was_class = creates_class
					break

		if len(chunk):
			raise InvalidRegexError("failed to parse %r" % chunk)

		#compile the character classes into a state machine
		#print ' '.join([str(c) for c in classes])
		next_state = self.initial_state = State()
		if not match_begin:
			self.initial_state.link(lambda c: True, self.initial_state, True)

		for i, c in enumerate(classes):
	
			state = next_state
			if i+1 == len(classes):
				if match_end:
					next_state = State()
					next_state.link(lambda c: c == '', SUCCESS, False)
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

	def match(self, s):
		result = self.initial_state.start(s)
		#print 'got', result
		return SUCCESS in result


if __name__ == '__main__':
	def test_regex(definition, cases):
		print 'testing', definition
		r = Regex(definition)
		for c, expected in cases:
			res = r.match(c)
			does_match = 'MATCH' if res else 'NO MATCH'
			print '   ', c.rjust(10) + ':', does_match.ljust(8), 'FAIL!!!' if res != expected else ''

	test_regex('a', [('a', True), ('b', False)])
	test_regex('abc', [('abc', True), ('xxabcxx', True), ('cab', False), ('aaa', False)])
	test_regex('ab?c', [('abc', True), ('ac', True), ('a', False), ('abbb', False), ('abbbc', False)])
	test_regex('ab*c', [('abc', True), ('ac', True), ('abbbbc', True), ('abbb', False), ('accc', True)])
	test_regex('ab+c', [('abc', True), ('abbbbc', True), ('ac', False), ('ab', False)])
	test_regex('ab{3}c', [('abbbc', True), ('abc', False), ('ac', False)])
	test_regex('ab{1,3}c', [('abc', True), ('abbc', True), ('abbbc', True), ('ac', False), ('abbbbc', False), ('abb', False)])
	test_regex('a[bc]*d', [('abcd', True), ('ad', True), ('abcbcccccd', True), ('addd', True)])
	test_regex('.*', [('abhsueoah', True), ('blahblah', True), ('test[', True), ('', True)])
	test_regex('aaa.*', [('aaahuetaot', True), ('aaa', True), ('blahbllah', False)])
	test_regex('a.*.*cc', [('aauoueoucc', True), ('abcc', True), ('acc', True), ('blahblah', False), ('xxcc', False)])
	test_regex('^abc', [('abc', True), ('abcdef', True), ('xxxabcxxx', False)])
	test_regex('abc$', [('abc', True), ('blahabc', True), ('abcblah', False)])
	test_regex('^abc$', [('abc', True), ('xxabc', False), ('abcxx', False)])
