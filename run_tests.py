#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Suite of unit-tests for testing Michel
"""
import unittest
import textwrap
import os
import sys
import tempfile
import datetime
import michel.michel as m

class TestMichel(unittest.TestCase):

    def test_format_google_dates(self):
        self.assertEqual("2015-12-09T00:00:00Z",
                         m.to_google_date_format(
                             datetime.datetime(2015, 12, 9, 20, 00)))
        self.assertEqual("2015-11-18T00:00:00Z",
                         m.to_google_date_format(
                             datetime.datetime(2015, 11, 18)))
        self.assertEqual("2015-12-10T00:00:00Z",
                         m.to_google_date_format(
                             datetime.datetime(2015, 12, 10, 3, 25)))
                         

    def test_format_emacs_dates(self):
        m.default_locale = 'Russian_Russia.1251'
        self.assertEqual("2015-12-09 Ср 20:00-21:00",
                         m.to_emacs_date_format(True,
                                           datetime.datetime(2015, 12, 9, 20, 00),
                                           datetime.datetime(2015, 12, 9, 21, 00)))
        
        m.default_locale = 'English_United States.1252'
        self.assertEqual("2015-11-18 Wed",
                         m.to_emacs_date_format(False,
                                           datetime.datetime(2015, 11, 18)))
        
        m.default_locale = 'German_Germany.1252'
        self.assertEqual("2015-12-10 Do 03:25",
                         m.to_emacs_date_format(True,
                                           datetime.datetime(2015, 12, 10, 3, 25)))

    def test_text_to_tasktree(self):
        # text should have trailing "\n" character, like most textfiles
        org_text = textwrap.dedent("""\
            * Headline 1
            Body 1a
                Body 1b
            * DONE    Headline 2
            ** Headline 2.1
            """)
        result_text = textwrap.dedent("""\
            * Headline 1
              Body 1a
              Body 1b
            * DONE Headline 2
            ** Headline 2.1
            """)
        tasktree = m.parse_text_to_tree(org_text)
        self.assertEqual(str(tasktree), result_text)

    def test_unicode_print(self):
        """
        Test ability to print unicode text
        """

        if os.name == 'nt':
            return
        
        unicode_task = {
            'status': 'needsAction',
            'kind': 'tasks#task',
            'title': 'السلام عليكم',
            'notes': 'viele Grüße',
            'id': 'ABC123',
        }
        tasks_tree = m.tasklist_to_tasktree([unicode_task])

        old_stdout = sys.stdout
        sys.stdout = open(os.devnull, 'w')
        try:
            tasks_tree._print()
        except UnicodeDecodeError:
            self.fail("TasksTree._print() raised UnicodeDecodeError")
        sys.stdout = old_stdout

    def test_unicode_dump_to_file(self):
        """
        Test ability to pull unicode text into orgfile
        """
        unicode_task = {
            'status': 'needsAction',
            'kind': 'tasks#task',
            'title': 'السلام عليكم',
            'notes': 'viele Grüße',
            'id': 'ABC123',
        }
        tasks_tree = m.tasklist_to_tasktree([unicode_task])

        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file_name = temp_file.name
            
        try:
            tasks_tree.write_to_orgfile(temp_file_name)
        except UnicodeDecodeError:
            self.fail("TasksTree.write_to_orgfile() raised UnicodeDecodeError")

    def test_initial_non_headline_text(self):
        """
        Test the case where the first lines of an org-mode file are not
        org-mode headlines.
        
        """
        # text should have trailing "\n" character, like most textfiles
        org_text = textwrap.dedent("""\

            Some non-headline text...
            Another line of it.
            * Headline 1
            Body 1a
                Body 1b
            * DONE    Headline 2
            ** Headline 2.1
            """)

        self.assertRaises(ValueError, m.parse_text_to_tree, org_text)

    def test_no_headlines(self):
        """
        Test the cases where there are no headlines at all in the file.
        
        """
        # text should have trailing "\n" character, like most textfiles
        org_text = textwrap.dedent("""\

            Some non-headline text...
            Another line of it.
            """)

        self.assertRaises(ValueError, m.parse_text_to_tree, org_text)

    def test_empty_file(self):
        org_text = "" # empty file
        m.parse_text_to_tree(org_text)
        
    def test_safemerge(self):
        org_text = textwrap.dedent("""\
            * Headline A1
            * Headline A2
            ** Headline A2.1
            * Headline B1
            ** Headline B1.1
               Remote append B1.1 body text.
            * Headline B2
            """)
        remote_text = textwrap.dedent("""\
            * Headline A1
            ** Headline A1.1
            * Headline B1
            ** Headline B1.1
               Remote append B1.1 body text.
            * Headline A2
            ** Headline A2.1
            * Headline B2 modified
              New B2 body text.
            """)
        result_text = textwrap.dedent("""\
            * Headline A1
            ** Headline A1.1
            * Headline A2
            ** Headline A2.1
            * Headline B1
            ** Headline B1.1
               Remote append B1.1 body text.
            * Headline B2 modified
              PREV_ORG_TITLE: Headline B2
              REMOTE_APPEND_NOTE: New B2 body text.
            """)
        
        org_tree = m.parse_text_to_tree(org_text)
        remote_tree = m.parse_text_to_tree(remote_text)
        m.treemerge(org_tree, remote_tree)
        
        self.assertEqual(str(org_tree), result_text)

    def test_remerge_with_fixes(self):
        m.default_locale = 'Russian_Russia.1251'
        org_text = textwrap.dedent("""\
            * Headline A1
              Original text.
            * TODO Headline B
            * TODO Headline C
              SCHEDULED: <2015-12-09 Ср 20:00-21:00>
            """)
        remote_text = textwrap.dedent("""\
            * Headline A1
              Original text.
              REMOTE_APPEND_NOTE: Text which should be ignored
            * TODO Headline C
              PREV_ORG_TITLE: Headline B
            * TODO Headline C
              SCHEDULED: <2015-12-09 Ср 19:00-20:00>
            """)
        result_text = textwrap.dedent("""\
            * Headline A1
              Original text.
            * TODO Headline B
            * TODO Headline C
              SCHEDULED: <2015-12-09 Ср 20:00-21:00>
            """)
        
        org_tree = m.parse_text_to_tree(org_text)
        remote_tree = m.parse_text_to_tree(remote_text)
        m.treemerge(org_tree, remote_tree)
        
        self.assertEqual(str(org_tree), result_text)

    def test_remerge_without_fixes(self):
        m.default_locale = 'Russian_Russia.1251'
        remote_text = textwrap.dedent("""\
            * Headline A1
              Original text.
              REMOTE_APPEND_NOTE: Text which should be ignored
            * TODO Headline C
              PREV_ORG_TITLE: Headline B
            * TODO Headline C
              SCHEDULED: <2015-12-09 Ср 19:00-20:00>
            """)
        org_text = remote_text
        result_text = remote_text
        
        org_tree = m.parse_text_to_tree(org_text)
        remote_tree = m.parse_text_to_tree(remote_text)
        m.treemerge(org_tree, remote_tree)
        
        self.assertEqual(str(org_tree), result_text)

    def test_merge_normalize_todo(self):
        org_text = textwrap.dedent("""\
            * Headline A
            ** Headline A1
            * Headline B
            ** TODO Headline B1
            * DONE Headline C
            ** TODO Headline C1
            * TODO Headline D
            """)
        result_text = textwrap.dedent("""\
            * Headline A
            ** Headline A1
            * TODO Headline B
            ** TODO Headline B1
            * TODO Headline C
            ** TODO Headline C1
            * TODO Headline D
            """)
        
        org_tree = m.parse_text_to_tree(org_text)
        self.assertEqual(str(org_tree), result_text)

    def test_merge_sync_todo_only(self):
        org_text = textwrap.dedent("""\
            * Headline A
            * Headline B
            * TODO Headline C
            * TODO Headline D
            * Headline E
            ** DONE Headline E1
            * DONE Headline F
            ** Headline F1
            """)
        remote_text = textwrap.dedent("""\
            * DONE Headline C
            * TODO Headline D
            """)
        result_text = textwrap.dedent("""\
            * Headline A
            * Headline B
            * DONE Headline C
              CLOSED: [{0}]
            * TODO Headline D
            * TODO Headline E
            ** DONE Headline E1
            * DONE Headline F
            ** Headline F1
            """.format(m.to_emacs_date_format(True, datetime.datetime.now())))
        
        org_tree = m.parse_text_to_tree(org_text)
        remote_tree = m.parse_text_to_tree(remote_text)
        m.treemerge(org_tree, remote_tree)
        
        self.assertEqual(str(org_tree), result_text)

    def test_scheduled_and_closed_time(self):
        m.default_locale = 'Russian_Russia.1251'
        org_text = textwrap.dedent("""\
            * Headline 1
              Normal notes
            * Headline 2
              SCHEDULED: <2015-11-18 Ср>
            * Headline 3
              SCHEDULED: <2015-12-09 Ср 19:00-20:00>
            * DONE Headline 4
              CLOSED: [2015-12-10 Чт 03:25]
            * DONE Headline 5
              CLOSED: [2015-12-10 Чт 03:25] SCHEDULED: <2015-12-09 Ср 03:00>
            """)
        tasktree = m.parse_text_to_tree(org_text)
        
        self.assertEqual(tasktree[0].closed_time, None)
        self.assertEqual(tasktree[0].scheduled_start_time, None)
        self.assertEqual(tasktree[0].scheduled_end_time, None)
        self.assertFalse(tasktree[0].scheduled_has_time)

        self.assertEqual(tasktree[1].closed_time, None)
        self.assertEqual(tasktree[1].scheduled_start_time, datetime.datetime(2015, 11, 18, 0, 0, tzinfo = m.LocalTzInfo()))
        self.assertEqual(tasktree[1].scheduled_end_time, None)
        self.assertEqual(m.to_google_date_format(tasktree[1].scheduled_start_time), "2015-11-18T00:00:00Z")
        self.assertFalse(tasktree[1].scheduled_has_time)

        self.assertEqual(tasktree[2].closed_time, None)
        self.assertEqual(tasktree[2].scheduled_start_time, datetime.datetime(2015, 12, 9, 19, 0, tzinfo = m.LocalTzInfo()))
        self.assertEqual(tasktree[2].scheduled_end_time, datetime.datetime(2015, 12, 9, 20, 0, tzinfo = m.LocalTzInfo()))
        self.assertEqual(m.to_google_date_format(tasktree[2].scheduled_start_time), "2015-12-09T00:00:00Z")
        self.assertTrue(tasktree[2].scheduled_has_time)

        self.assertEqual(tasktree[3].closed_time, datetime.datetime(2015, 12, 10, 3, 25, tzinfo = m.LocalTzInfo()))
        self.assertEqual(tasktree[3].scheduled_start_time, None)
        self.assertEqual(tasktree[3].scheduled_end_time, None)
        self.assertFalse(tasktree[3].scheduled_has_time)

        self.assertEqual(tasktree[4].closed_time, datetime.datetime(2015, 12, 10, 3, 25, tzinfo = m.LocalTzInfo()))
        self.assertEqual(tasktree[4].scheduled_start_time, datetime.datetime(2015, 12, 9, 3, 0, tzinfo = m.LocalTzInfo()))
        self.assertEqual(tasktree[4].scheduled_end_time, None)
        self.assertEqual(m.to_google_date_format(tasktree[4].scheduled_start_time), "2015-12-09T00:00:00Z")
        self.assertTrue(tasktree[4].scheduled_has_time)
                         
        self.assertEqual(str(tasktree), org_text)

    def test_sync_time(self):
        m.default_locale = 'Russian_Russia.1251'
        org_text = textwrap.dedent("""\
            * TODO Headline A
            * TODO Headline B
            * TODO Headline C
              SCHEDULED: <2015-12-09 Ср 20:00-21:00>
            """)
        remote_text = textwrap.dedent("""\
            * TODO Headline A
              SCHEDULED: <2015-12-09 Ср>
            * TODO Headline B
            * DONE Headline C
              SCHEDULED: <2015-12-09 Ср 20:00-21:00>
            * TODO Headline D
              SCHEDULED: <2015-12-09 Ср>
            """)
        
        result_text = textwrap.dedent("""\
            * TODO Headline A
              SCHEDULED: <2015-12-09 Ср>
            * TODO Headline B
            * DONE Headline C
              CLOSED: [{0}] SCHEDULED: <2015-12-09 Ср 20:00-21:00>
            * TODO Headline D
              SCHEDULED: <2015-12-09 Ср>
            """.format(m.to_emacs_date_format(True, datetime.datetime.now())))
        
        org_tree = m.parse_text_to_tree(org_text)
        remote_tree = m.parse_text_to_tree(remote_text)
        m.treemerge(org_tree, remote_tree)
        
        self.assertEqual(str(org_tree), result_text)


if __name__ == '__main__':
    unittest.main()
