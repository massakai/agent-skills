"""公開入力からの依存方向・状態保持・本文保全を検査する。"""

from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('render_graph', Path(__file__).parents[1] / 'scripts/render_graph.py')
GRAPH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRAPH)


def snapshot():
    """別repositoryの同番号を含む架空の入力を返す。"""
    def node(repo, status, kind, blocked_by):
        return dict(url=f'https://github.com/example/{repo}/issues/2', title='確認 " <img> #{}',
                    status=status, status_reason='選択Projectから取得', kind=kind, state='OPEN', blocked_by=blocked_by)
    return dict(complete=True, scope='direct', root_url='https://github.com/example/demo/issues/1',
                captured_at='2026-01-01T10:00:00+09:00', status_source='Project example/2 / Status',
                omitted_closed=[], nodes=[node('demo', 'In Review', 'child', ['https://github.com/example/other/issues/2']),
                                          node('other', 'Custom status', 'boundary', [])])


class RenderGraphTest(unittest.TestCase):
    def test_cross_repository_same_number_preserves_native_direction(self):
        # Given
        data = snapshot()
        # When
        result = GRAPH.render(data)
        # Then
        self.assertIn('n1 --> n0', result)

    def test_unknown_project_status_is_not_coerced(self):
        # When
        result = GRAPH.render(snapshot())
        # Then
        self.assertIn('<br/>Custom status', result)

    def test_external_title_is_encoded(self):
        # When
        result = GRAPH.render(snapshot())
        # Then
        self.assertIn('確認 #34; #60;img#62; #35;#123;#125;', result)

    def test_body_outside_markers_is_preserved(self):
        # Given
        body = '前文\n' + GRAPH.START + '\n旧図\n' + GRAPH.END + '\n後文'
        block = GRAPH.render(snapshot())
        # When
        result = GRAPH.update_body(body, block)
        # Then
        self.assertEqual(result, '前文\n' + block + '\n後文')

    def test_timestamp_only_change_does_not_update_body(self):
        # Given
        data = snapshot()
        body = GRAPH.render(data)
        data['captured_at'] = '2026-01-02T10:00:00+09:00'
        # When
        result = GRAPH.update_body(body, GRAPH.render(data))
        # Then
        self.assertEqual(result, body)

    def test_missing_markers_refuse_body_replacement(self):
        # When / Then
        with self.assertRaises(ValueError):
            GRAPH.update_body('手書き本文', GRAPH.render(snapshot()))

    def test_incomplete_pages_refuse_graph(self):
        # Given
        data = snapshot()
        data['complete'] = False
        # When / Then
        with self.assertRaises(ValueError):
            GRAPH.render(data)

    def test_unfetched_dependency_refuses_graph(self):
        # Given
        data = snapshot()
        data['nodes'][0]['blocked_by'] = ['https://github.com/example/demo/issues/99']
        # When / Then
        with self.assertRaises(ValueError):
            GRAPH.render(data)

    def test_cycle_refuses_graph(self):
        # Given
        data = snapshot()
        data['nodes'][1]['blocked_by'] = [data['nodes'][0]['url']]
        # When / Then
        with self.assertRaises(ValueError):
            GRAPH.render(data)

    def test_done_open_disagreement_is_reported(self):
        # Given
        data = snapshot()
        data['nodes'][0]['status'] = 'Done'
        # When
        result = GRAPH.render(data)
        # Then
        self.assertIn('Issue OPEN / Status Done', result)

    def test_unknown_status_keeps_reason(self):
        # Given
        data = snapshot()
        data['nodes'][0].update(status='Unknown', status_reason='選択Projectに未登録')
        # When
        result = GRAPH.render(data)
        # Then
        self.assertIn('選択Projectに未登録', result)

    def test_unknown_closed_is_not_classified_as_status_disagreement(self):
        # Given
        data = snapshot()
        data['nodes'][0].update(status='Unknown', state='CLOSED', status_reason='選択Projectに未登録')
        # When
        result = GRAPH.render(data)
        # Then
        self.assertNotIn('状態要照合:', result)

    def test_source_order_does_not_change_graph(self):
        # Given
        data = snapshot()
        reordered = deepcopy(data)
        reordered['nodes'].reverse()
        # When
        result = GRAPH.render(reordered)
        # Then
        self.assertEqual(result, GRAPH.render(data))


if __name__ == '__main__':
    unittest.main()
