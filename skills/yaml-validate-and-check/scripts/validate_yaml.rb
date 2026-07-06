#!/usr/bin/env ruby
# frozen_string_literal: true

require "psych"

def usage
  warn "Usage: ruby scripts/validate_yaml.rb <file.yml>"
  exit 1
end

path = ARGV[0]
usage unless path

content = File.read(path)

begin
  stream = Psych.parse_stream(content, path)
rescue Psych::SyntaxError => e
  warn "YAML syntax error in #{path}:"
  warn e.message
  exit 1
end

warnings = []

walk = lambda do |node, path_parts|
  case node
  when Psych::Nodes::Document
    walk.call(node.root, path_parts) if node.root
  when Psych::Nodes::Mapping
    seen = {}
    children = node.children
    index = 0

    while index < children.length
      key_node = children[index]
      value_node = children[index + 1]

      key =
        if key_node.is_a?(Psych::Nodes::Scalar)
          key_node.value
        else
          "<non-scalar-key>"
        end

      full_path = (path_parts + [key]).join(".")
      warnings << "duplicate key: #{full_path}" if seen[key]
      seen[key] = true

      walk.call(value_node, path_parts + [key]) if value_node
      index += 2
    end
  when Psych::Nodes::Sequence
    node.children.each_with_index do |child, child_index|
      walk.call(child, path_parts + ["[#{child_index}]"])
    end
  end
end

documents = stream.children.grep(Psych::Nodes::Document)
documents.each_with_index do |document, index|
  walk.call(document, ["doc#{index}"])
end

if warnings.empty?
  puts "YAML parse: OK"
  puts "Documents: #{documents.length}"
  documents.each_with_index do |document, index|
    root = document.root
    root_type = root ? root.class.name.split("::").last : "Empty"
    puts "doc#{index} root: #{root_type}"
  end
  exit 0
end

warn "YAML parse: OK"
warn "Duplicate keys detected:"
warnings.each { |warning| warn "- #{warning}" }
exit 2
