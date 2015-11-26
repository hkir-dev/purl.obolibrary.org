#!/usr/bin/env python3
#
# Reads a YAML file with a list of `purl_rules`
# and writes Apache mod_alias RedirectMatch directives. See:
#
# https://httpd.apache.org/docs/2.4/mod/mod_alias.html
#
# There are four types of rules:
#
# - path: match an exact URL string
#   and redirect to an exact URL
# - prefix: match a URL prefix string,
#   from the start of the request URL,
#   and redirect to the "replacement" field plus
#   any string following the prefix in the request
# - regex: use any regular expression
#   allowed by RedirectMatch
# - term_browser: special configuration for Ontobee, etc.
#
# Rules can have these fields:
#
# - path/prefix/regex: the URL string or regex to match;
#   pathly one required;
#   should begin with a slash "/obo/idspace" except for some regexs
# - term_browser: currently must be "ontobee"
# - replacement: the URL string or regex to redirect to;
#   exactly one required except for `term_browser` rules
# - level: either 'project' or 'top';
#   this field is required for `regex` rules
# - status: HTTP status for redirect;
#   zero or one value; defaults to "temporary";
#   can be "permanent" (301), "temporary" (302), or "see other" (303)
# - tests: used by test.py
#
# See the `tools/config.schema.yml` for more details.
#
# For the "path" and "prefix" types,
# the URL strings are rewritten as escaped regular expressions,
# with a "^" prefix and a "$" suffix.
# Any regular expression special characters (e.g. ., *, ?, [])
# will be escaped: they will not match as regular expressions.
#
# For the "prefix" type, "(.*)" is also appended to the "prefix" field
# and "$1" is appended to the "to" field,
# to configure the prefix match.
#
# For the "regex" type, the "" and "to" fields
# are assumed to be valid regular expressions,
# and are not checked or modified.
#
# **Only** use "regex" if "path" or "prefix" are insufficient.
#
# The order of YAML objects will be the order
# of the Apache directives.
# If no rules are found,
# the generated file will have a header comment
# without any directives.

import argparse, sys, yaml, os.path, re, pytest

project_template = '''# DO NOT EDIT THIS FILE!
# Automatically generated from "%s".
# Edit that source file then regenerate this file.

'''
top_template = '''# Top-level rules for %s
'''

# Parse command line arguments,
# read rules from the YAML file,
# and write the Apache .htaccess file.
def main():
  parser = argparse.ArgumentParser(description='Translate YAML `rules` to .htaccess')
  parser.add_argument('mode',
      type=str,
      help='processing mode: "project" or "top"')
  parser.add_argument('yaml_file',
      type=argparse.FileType('r'),
      help='read from the YAML file')
  parser.add_argument('htaccess_file',
      type=argparse.FileType('w'),
      default=sys.stdout,
      nargs='?',
      help='write to the .htaccess file (or STDOUT)')
  args = parser.parse_args()

  mode = args.mode.lower()
  yaml_file_base_name = os.path.basename(args.yaml_file.name)
  idspace = os.path.splitext(yaml_file_base_name)[0]

  document = yaml.load(args.yaml_file)
  if 'purl_rules' in document and type(document['purl_rules']) is list:
    if mode == 'project':
      args.htaccess_file.write(project_template % args.yaml_file.name)
    elif mode == 'top':
      args.htaccess_file.write(top_template % idspace)
    else:
      raise ValueError('Processing mode must be "project" or "top", not "%s"', mode)

    for rule in document['purl_rules']:
      result = process_rule(mode, idspace, rule)
      if result:
        args.htaccess_file.write(result + '\n')

    if mode == 'top':
        args.htaccess_file.write('\n')

  else:
    raise ValueError('No `purl_rules` found in %s' % args.yaml_file.name)


def clean_source(s):
  """Given a URL string,
  return an escaped regular expression for matching that string.
  Only forward-slashes are not escaped."""
  r = s.strip()
  r = re.escape(r)
  r = r.replace('\\/', '/')
  return r


def process_rule(processing_level, idspace, rule):
  """Given a processing level, an idspace, and an rule dictionary,
  ensure that the rule is valid,
  and return an Apache RedirectMatch directive string."""
  base_url = '/obo/' + idspace.lower()
  if idspace == 'OBO':
    base_url = '/obo'
  path = ''
  prefix = ''
  source = ''
  replacement = ''
  rule_level = 'top'
  status = 'temporary'

  # Check rule data type
  if type(rule) is not dict:
    raise ValueError('Not a YAML map:\n%s' % rule)

  # Determine the type for this rule
  types = []
  if 'path' in rule:
    types.append('path')
  if 'prefix' in rule:
    types.append('prefix')
  if 'regex' in rule:
    types.append('regex')
  if 'term_browser' in rule:
    types.append('term_browser')

  # Ensure that there is no more than one "type" key
  if len(types) < 1:
    raise ValueError('Rule does not have a valid type:\n%s' % rule)
  elif len(types) > 1:
    raise ValueError('Rule has multiple types: %s\n%s' % (', '.join(types), rule))
  rule_type = types[0]

  # Validate "replacement" field
  if rule_type == 'term_browser':
    if 'replacement' in rule:
      raise ValueError('term_browser rules do not use "replacement":\n' % rule)
  else:
    if not 'replacement' in rule or rule['replacement'].strip() == '':
      raise ValueError('Missing "replacement" field:\n' % rule)

  # Handle rule
  if rule_type == 'path':
    path = rule['path']
    source = '(?i)^%s$' % clean_source(rule['path'])
    replacement = rule['replacement']
  elif rule_type == 'prefix':
    prefix = rule['prefix']
    source = '(?i)^%s(.*)$' % clean_source(rule['prefix'])
    replacement = rule['replacement'] + '$1'
  elif rule_type == 'regex':
    if not 'level' in rule:
      raise ValueError('regex rule must have a "level":\n%s' % rule)
    source = rule['regex']
    replacement = rule['replacement']
  elif rule_type == 'term_browser':
    if rule['term_browser'].lower() == 'ontobee':
      source = '(?i)^/obo/%s_(\d+)$' % idspace
      replacement = "http://www.ontobee.org/browser/rdf.php?o=%s&iri=http://purl.obolibrary.org/obo/%s_$1" % (idspace, idspace)
      rule_level = 'top'
      status = 'see other'
    else:
      raise ValueError('Unknown term_browser "%s":\n%s' % (rule['term_browser'], rule))

  # Ensure that rules are in the right IDSPACE
  if rule_type == 'path' and not path.lower().startswith(base_url):
    raise ValueError('Bad path "%s" for IDSPACE "%s":\n%s' % (path, idspace, rule))
  if rule_type == 'prefix' and not prefix.lower().startswith(base_url):
    raise ValueError('Bad prefix "%s" for IDSPACE "%s":\n%s' % (prefix, idspace, rule))

  # Determine the rule_level for the rule: project or top
  if 'level' in rule:
    if rule['level'].lower() in ('project', 'top'):
      rule_level = rule['level'].lower()
    else:
      raise ValueError('Level must be "project" or "top", not "%s":\n%s' % (rule['level'], rule))
  elif path.lower().startswith(base_url + '/'):
    rule_level = 'project'
  elif prefix.lower().startswith(base_url + '/'):
    rule_level = 'project'
  elif rule_type == 'term_browser':
    rule_level = 'top'

  # Do not process TOP rules when in PROJECT mode
  if processing_level == 'project' and rule_level == 'top':
    return None

  # Do not process PROJECT rules when in TOP mode
  if processing_level == 'top' and rule_level == 'project':
    return None

  # Even in TOP mode, only certain TOP paths are allowed:
  # - allow all regex rules, because we can't check them.
  # - allow term_browser rules
  # - allow /obo/idspace base redirects
  # - allow /obo/idspace.owl and /obo/idspace.obo paths.
  # - allow /obo/idspace_ prefixes (for terms)
  if processing_level == 'top':
    if rule_type == 'regex' \
      or rule_type == 'term_browser' \
      or path == base_url \
      or path == base_url + '.owl' \
      or path == base_url + '.obo' \
      or prefix == '/obo/%s_' % idspace:
      pass
    else:
      raise ValueError('Invalid top-level rule for IDSPACE "%s":\n%s' % (idspace, rule))

  # Validate status code
  if 'status' in rule:
    if rule['status'] in ('permanent', 'temporary', 'see other'):
      status = rule['status']
    else:
      raise ValueError('Invalid status "%s" for rule:\n%s' % (rule['status'], rule))

  # Switch to Apache's preferred names
  if status == 'temporary':
    status = 'temp'
  elif status == 'see other':
    status = 'seeother'

  # Return an Apache RedirectMatch directive string
  return 'RedirectMatch %s "%s" "%s"' % (status, source, replacement)


# Unit Tests
def test_missing_type():
  with pytest.raises(ValueError):
    process_rule('project', 'OBI', {'replacement': 'foo'})

def test_multiple_types():
  with pytest.raises(ValueError):
    process_rule('project', 'OBI', {'path': 'foo', 'prefix': 'foo'})

def test_term_browser_replacement():
  with pytest.raises(ValueError):
    process_rule('top', 'OBI', {'term_browser': 'ontobee', 'replacement': 'foo'})

def test_regex_without_level():
  with pytest.raises(ValueError):
    process_rule('top', 'OBI', {'regex': 'foo', 'replacement': 'foo'})

def test_invalid_term_browser():
  with pytest.raises(ValueError):
    process_rule('top', 'OBI', {'term_browser': 'foo'})

def test_idspace_crosstalk():
  with pytest.raises(ValueError):
    process_rule('project', 'OBI', {'path': '/obo/chebi/', 'replacement': 'foo'})

def test_level_crosstalk():
  assert(process_rule('project', 'OBI', {'path': '/obo/obi', 'replacement': 'foo'}) == None)
  assert(process_rule('top', 'OBI', {'path': '/obo/obi/', 'replacement': 'foo'}) == None)

def test_top_level_pollution():
  with pytest.raises(ValueError):
    process_rule('top', 'OBI', {'path': '/obo/obi_core.owl', 'replacement': 'foo'})

def test_invalid_level():
  with pytest.raises(ValueError):
    process_rule('project', 'OBI', {'level': 'bar', 'path': 'foo', 'replacement': 'foo'})


# Run main()
if __name__ == "__main__":
    main()