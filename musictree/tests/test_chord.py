import copy
from unittest import skip

from quicktions import Fraction

from musictree import BassClef, Score
from musictree.accidental import Accidental
from musictree.beat import Beat
from musictree.chord import Chord, split_copy, group_chords
from musictree.exceptions import ChordHasNoParentError, DeepCopyException, ChordNotesAreAlreadyCreatedError, \
    ChordException
from musictree.midi import Midi
from musictree.quarterduration import QuarterDuration
from musictree.tests.util import ChordTestCase, create_articulation, create_technical, create_ornament
from musictree.util import XML_ARTICULATION_CLASSES, XML_TECHNICAL_CLASSES, XML_DYNAMIC_CLASSES, XML_ORNAMENT_CLASSES, \
    XML_OTHER_NOTATIONS, XML_DIRECTION_TYPE_CLASSES
from musicxml.xmlelement.xmlelement import *


def get_chord_midi_values(chord):
    return [m.value for m in chord._midis]


class TestTreeChord(ChordTestCase):

    def test_mocks(self):
        assert self.mock_voice.number == 1
        assert self.mock_beat.up.number == 1
        ch = Chord()
        ch._parent = self.mock_beat
        assert ch.up == self.mock_beat
        assert ch.up.up == self.mock_voice
        assert ch.up.up.up == self.mock_staff
        assert ch.up.up.up.up == self.mock_measure
        assert ch.get_parent_measure() == self.mock_measure

    def test_chord_init_midis(self):
        """
        Test all possible types of input midis
        """
        ch = Chord(70, 1)
        assert get_chord_midi_values(ch) == [70]
        ch = Chord([70, 50], 1)
        assert get_chord_midi_values(ch) == [50, 70]
        ch = Chord(0, 1)
        assert get_chord_midi_values(ch) == [0]
        ch = Chord(Midi(90, accidental=Accidental(mode='enharmonic')), 1)
        assert get_chord_midi_values(ch) == [90]
        ch = Chord([Midi(90, accidental=Accidental(mode='enharmonic')), 70], 1)
        assert get_chord_midi_values(ch) == [70, 90]

        with self.assertRaises(ValueError):
            Chord([0, 60], 1)

        """
        A grace note cannot be a rest.
        """
        with self.assertRaises(ValueError):
            Chord(0, 0)

    def test_chord_needs_parent_error(self):
        ch = Chord(70, 1)
        with self.assertRaises(ChordHasNoParentError):
            ch.finalize()
        ch._parent = self.mock_beat
        ch.finalize()

    def test_init_quarter_durations(self):
        """
        Test values of quarter_duration
        """
        ch = Chord(90, 1.25)
        assert ch.quarter_duration == 1.25
        ch = Chord(80, 1.2)
        assert ch.quarter_duration == Fraction(1.2)
        assert ch.quarter_duration == 1.2
        assert ch.quarter_duration == Fraction(6 / 5)
        assert ch.quarter_duration == 6 / 5
        ch = Chord(80, 8)
        assert ch.quarter_duration == 8
        with self.assertRaises(TypeError):
            ch = Chord(80, '1.2')
        ch = Chord(70, Fraction(1, 4))
        assert ch.quarter_duration == 0.25
        ch = Chord(70, QuarterDuration(1, 4))
        assert ch.quarter_duration == 0.25

    def test_is_rest(self):
        """
        Test is_rest property
        """
        assert Chord(0, 1).is_rest
        assert not Chord(50, 1).is_rest

    def test_chord_attributes(self):
        """
        Test that a dot operator can set and get note attributes
        """
        c = Chord([60, 61, 62], 2)
        c._parent = self.mock_beat
        c.finalize()
        c.relative_x = 10
        assert c.relative_x == [10, 10, 10]
        c.relative_y = [None, 20, 10]
        assert c.relative_y == [None, 20, 10]
        c.relative_y = [10]
        assert c.relative_y == [10, 20, 10]
        c.default_y = [10]
        assert c.default_y == [10, None, None]

    def test_chord_one_note(self):
        c = Chord(70, 4, relative_x=10)
        c.midis[0].accidental.show = True
        c._parent = self.mock_beat
        c.finalize()
        expected = """<note relative-x="10">
  <pitch>
    <step>B</step>
    <alter>-1</alter>
    <octave>4</octave>
  </pitch>
  <duration>4</duration>
  <voice>1</voice>
  <type>whole</type>
  <accidental>flat</accidental>
</note>
"""
        assert c.notes[0].to_string() == expected
        c.midis[0].value = 72
        expected = """<note relative-x="10">
  <pitch>
    <step>C</step>
    <octave>5</octave>
  </pitch>
  <duration>4</duration>
  <voice>1</voice>
  <type>whole</type>
  <accidental>natural</accidental>
</note>
"""
        assert c.notes[0].to_string() == expected
        # change chord's midi (zero)
        c.midis[0].value = 0
        # c.finalize()

        expected = """<note relative-x="10">
  <rest />
  <duration>4</duration>
  <voice>1</voice>
  <type>whole</type>
</note>
"""
        assert c.notes[0].to_string() == expected
        c = Chord(midis=0, quarter_duration=2)
        # change chord's duration (not zero)
        c.quarter_duration = 1
        c._parent = self.mock_beat
        c.finalize()
        expected = """<note>
  <rest />
  <duration>1</duration>
  <voice>1</voice>
  <type>quarter</type>
</note>
"""
        assert c.notes[0].to_string() == expected
        c = Chord(0, 1)
        # change chord's duration (zero)
        with self.assertRaises(ValueError):
            c.quarter_duration = 0
        c.midis[0].value = 60
        # c.quarter_duration = 0
        # c._parent = self.mock_beat

    def test_chord_single_non_rest(self):
        """
        Test a chord with a non rest single midi
        """
        c = Chord(72, 2)
        c.midis[0].accidental.show = True
        c._parent = self.mock_beat
        c.finalize()

        c.xml_type = '16th'
        c.xml_stem = 'up'
        c.xml_staff = 1

        expected = """<note>
  <pitch>
    <step>C</step>
    <octave>5</octave>
  </pitch>
  <duration>2</duration>
  <voice>1</voice>
  <type>16th</type>
  <accidental>natural</accidental>
  <stem>up</stem>
  <staff>1</staff>
</note>
"""
        assert c.notes[0].to_string() == expected
        c.midis[0].value = 61
        expected = """<pitch>
  <step>C</step>
  <alter>1</alter>
  <octave>4</octave>
</pitch>
"""
        assert c.notes[0].xml_pitch.to_string() == expected
        c.midis[0].value = 0
        # c.finalize()
        assert c.notes[0].xml_pitch is None
        assert c.notes[0].xml_rest is not None
        assert c.is_rest

    def test_chord_single_non_rest_midi_with_accidental(self):
        """
        Test chord with a non rest single midi with accidental set.
        """
        chord = Chord(Midi(70, accidental=Accidental(mode='sharp')), 1)
        chord._parent = self.mock_beat
        chord.finalize()
        expected = """<pitch>
    <step>A</step>
    <alter>1</alter>
    <octave>4</octave>
  </pitch>
"""
        assert chord.notes[0].xml_pitch.to_string() == expected

    def test_chord_as_rest(self):
        """
        Test chord with a rest midi
        """
        chord = Chord(0, 2)
        chord._parent = self.mock_beat
        expected = """<note>
  <rest />
  <duration>2</duration>
  <voice>1</voice>
  <type>half</type>
</note>
"""

        chord.finalize()
        assert chord.notes[0].to_string() == expected
        chord.midis = [60, 61]
        expected = """<pitch>
    <step>C</step>
    <octave>4</octave>
  </pitch>
"""
        assert chord.notes[0].xml_pitch.to_string() == expected
        expected = """<pitch>
    <step>C</step>
    <alter>1</alter>
    <octave>4</octave>
  </pitch>
"""
        assert chord.notes[1].xml_pitch.to_string() == expected

    def test_chord_to_rest(self):
        chord = Chord(60, 2)
        chord._parent = self.mock_beat
        chord.finalize()
        chord.to_rest()
        expected = """<note>
  <rest />
  <duration>2</duration>
  <voice>1</voice>
  <type>half</type>
</note>
"""
        assert chord.notes[0].to_string() == expected
        assert len(chord.notes) == 1

    def test_chord_with_multiple_midis(self):
        """
        Test chord with a list of midis
        """

        chord = Chord([60, 62, 63], 2)
        chord.midis[1].accidental.show = True
        chord.midis[2].accidental.show = True
        chord._parent = self.mock_beat
        chord.finalize()
        chord.xml_stem = 'up'
        expected_1 = """<note>
  <pitch>
    <step>C</step>
    <octave>4</octave>
  </pitch>
  <duration>2</duration>
  <voice>1</voice>
  <type>half</type>
  <stem>up</stem>
</note>
"""
        expected_2 = """<note>
  <chord />
  <pitch>
    <step>D</step>
    <octave>4</octave>
  </pitch>
  <duration>2</duration>
  <voice>1</voice>
  <type>half</type>
  <accidental>natural</accidental>
  <stem>up</stem>
</note>
"""
        expected_3 = """<note>
  <chord />
  <pitch>
    <step>E</step>
    <alter>-1</alter>
    <octave>4</octave>
  </pitch>
  <duration>2</duration>
  <voice>1</voice>
  <type>half</type>
  <accidental>flat</accidental>
  <stem>up</stem>
</note>
"""
        for note, expected in zip(chord.notes, [expected_1, expected_2, expected_3]):
            assert note.to_string() == expected

    def test_group_chords(self):
        chords = [Chord(60, qd) for qd in [1 / 6, 1 / 6, 1 / 6, 1 / 10, 3 / 10, 1 / 10]]
        with self.assertRaises(ValueError):
            assert group_chords(chords, [1 / 2, 1 / 2, 1 / 2])
        assert group_chords(chords, [1 / 2, 1 / 2]) == [chords[:3], chords[3:]]
        assert group_chords(chords, [1 / 3, 2 / 3]) == [chords[:2], chords[2:]]
        assert group_chords(chords, [1 / 4, 3 / 4]) is None

    def test_has_same_pitches(self):
        ch1 = Chord([60, Midi(61), 62], 1)
        ch2 = Chord([60, Midi(61)], 1)
        assert not ch1.has_same_pitches(ch2)
        ch2 = Chord([60, Midi(61), 62], 1)
        assert ch1.has_same_pitches(ch2)
        ch2 = Chord([60, Midi(61, accidental=Accidental(mode='flat')), 62], 1)
        assert not ch1.has_same_pitches(ch2)

    def test_add_lyric(self):
        ch = Chord(60, 2)
        ch._parent = self.mock_beat
        ch.add_lyric('test')
        ch.finalize()
        assert ch.notes[0].xml_lyric is not None
        assert ch.notes[0].xml_lyric.xml_text.value_ == 'test'

    def test_add_lyrics_after_creating_notes(self):
        ch = Chord(60, 1)
        ch._parent = self.mock_beat
        lyrics1 = ch.add_lyric('one')
        ch.finalize()
        lyrics2 = ch.add_lyric('two')
        assert ch.notes[0].find_children('XMLLyric') == [lyrics1, lyrics2]

    def test_get_staff_number(self):
        ch = Chord(60, 2)
        ch._parent = self.mock_beat
        assert ch.get_staff_number() is None
        self.mock_staff.number = 1
        assert ch.get_staff_number() == 1

    def test_add_articulation_after_creating_notes(self):
        ch = Chord(60, 1)
        ch._parent = self.mock_beat
        staccato = ch.add_x(create_articulation(XMLStaccato))
        ch.finalize()
        assert isinstance(ch.notes[0].xml_notations.xml_articulations.get_children()[0], XMLStaccato)
        accent = ch.add_x(create_articulation(XMLAccent))
        assert ch.notes[0].xml_notations.xml_articulations.get_children() == [staccato, accent]

    def test_add_multiple_articulations(self):
        articulation_classes = XML_ARTICULATION_CLASSES[:3]
        ch = Chord(60, 1)
        ch._parent = self.mock_beat
        for a in articulation_classes:
            ch.add_x(a())
        assert len(ch._xml_articulations) == 3
        ch.finalize()
        n = ch.notes[0]
        assert n.xml_notations.xml_articulations is not None
        assert [type(a) for a in n.xml_notations.xml_articulations.get_children()] == articulation_classes

    def test_add_xml_wedge_objects(self):
        wedges = [XMLWedge(type=val) for val in ['crescendo', 'stop', 'diminuendo', 'stop']]
        for wedge in wedges:
            ch = Chord(60, 4)
            ch._parent = self.mock_beat
            ch.add_wedge(wedge)
            ch.finalize()
            assert len(ch._xml_directions) == 1
            d = ch._xml_directions[0]
            assert d.placement == 'below'
            assert d.xml_direction_type.xml_wedge == wedge

    def test_add_wedge_string(self):
        wedges = ['crescendo', 'stop', 'diminuendo', 'stop']
        for wedge in wedges:
            ch = Chord(60, 4)
            ch._parent = self.mock_beat
            ch.add_wedge(wedge)
            ch.finalize()
            assert len(ch._xml_directions) == 1
            d = ch._xml_directions[0]
            assert d.placement == 'below'
            assert d.xml_direction_type.xml_wedge.type == wedge

    @skip
    def test_add_words(self):
        self.fail('Incomplete')

    def test_add_clef(self):
        ch = Chord(60, 2)
        assert ch.clef is None
        cl = BassClef()
        ch.clef = cl
        assert ch.clef == cl
        with self.assertRaises(TypeError):
            ch.clef = 'bla'

    @skip
    def test_add_bracket(self):
        self.fail('Incomplete')

    @skip
    def test_add_grace_chords(self):
        self.fail('Incomplete')

    @skip
    def test_percussion_notation(self):
        self.fail('Incomplete')

    @skip
    def test_finger_tremolo(self):
        self.fail('Incomplete')

    def test_chord_add_x_as_object_articulation(self):
        for cls in XML_ARTICULATION_CLASSES:
            ch = Chord(60, 1)
            ch.add_x(create_articulation(cls))
            ch._parent = self.mock_beat
            ch.finalize()
            assert isinstance(ch.notes[0].xml_notations.xml_articulations.get_children()[0], cls)

    def test_chord_add_x_as_object_technical(self):
        for cls in XML_TECHNICAL_CLASSES:
            ch = Chord(60, 1)
            ch.add_x(create_technical(cls))
            ch._parent = self.mock_beat
            ch.finalize()
            assert isinstance(ch.notes[0].xml_notations.xml_technical.get_children()[0], cls)

    def test_chord_add_x_as_object_dynamics(self):
        for cls in XML_DYNAMIC_CLASSES:
            ch = Chord(60, 1)
            ch.add_x(cls())
            ch._parent = self.mock_beat
            ch.finalize()
            assert isinstance(ch.notes[0].xml_notations.xml_dynamics.get_children()[0], cls)

    def test_chord_add_x_as_object_ornaments(self):
        for cls in XML_ORNAMENT_CLASSES[1:]:
            ch = Chord(60, 1)
            ch.add_x(create_ornament(cls))
            ch._parent = self.mock_beat
            ch.finalize()
            assert isinstance(ch.notes[0].xml_notations.xml_ornaments.get_children()[0], cls)

    def test_chord_add_x_trill_with_wavy_line_and_accidental_mark(self):
        ch = Chord(60, 1)
        ch.add_x(XMLTrillMark())
        ch.add_x(XMLAccidentalMark('sharp'))
        ch.add_x(XMLWavyLine(type='start', relative_x=0))
        ch.add_x(XMLWavyLine(type='stop', relative_x=20))
        ch._parent = self.mock_beat
        ch.finalize()
        expected = """<ornaments>
      <trill-mark />
      <accidental-mark>sharp</accidental-mark>
      <wavy-line type="start" relative-x="0" />
      <wavy-line type="stop" relative-x="20" />
    </ornaments>
"""
        assert ch.notes[0].xml_notations.xml_ornaments.to_string() == expected

    def test_chord_add_x_as_object_other_notations(self):
        for cls in XML_OTHER_NOTATIONS:
            ch = Chord(60, 1)
            ch.add_x(cls())
            ch._parent = self.mock_beat
            ch.finalize()
            assert isinstance(ch.notes[0].xml_notations.get_children()[0], cls)

    def test_deepcopy_chord(self):
        chord = Chord([60, 62], 2)
        chord.add_tie('start')
        copied = copy.deepcopy(chord)
        assert [midi.value for midi in copied.midis] == [midi.value for midi in chord.midis]
        assert [id(midi) for midi in copied.midis] != [id(midi) for midi in chord.midis]
        assert chord.quarter_duration.value == copied.quarter_duration.value
        assert id(chord.quarter_duration) != id(copied.quarter_duration)
        chord._parent = self.mock_beat
        chord.finalize()
        with self.assertRaises(DeepCopyException):
            copy.deepcopy(chord)
        # chord.add_dynamics('p')
        # chord.add_lyric('something')
        # chord.add_x(XMLAccent())
        # chord.add_x(XMLUpBow())
        # chord.add_x(XMLAccidentalMark())
        # chord.add_x(XMLFf())

    def test_add_midi(self):
        chord = Chord([60, 62], 2)
        m = Midi(63)
        chord.add_midi(m)
        assert [midi.value for midi in chord.midis] == [60, 62, 63]
        assert chord.midis[-1] == m
        chord.add_midi(58)
        assert [midi.value for midi in chord.midis] == [58, 60, 62, 63]
        chord.add_midi(60)
        assert [midi.value for midi in chord.midis] == [58, 60, 60, 62, 63]

        chord._parent = self.mock_beat
        chord.finalize()
        with self.assertRaises(ChordNotesAreAlreadyCreatedError):
            chord.add_midi(80)

    def test_add_direction_type(self):
        score = Score()
        p = score.add_part('part-1')
        for dt_class in XML_DIRECTION_TYPE_CLASSES:
            chord = Chord(midis=60, quarter_duration=4)
            if dt_class == XMLSymbol:
                dt_obj = dt_class('0')
            else:
                dt_obj = dt_class()
            if dt_class == XMLDynamics:
                assert self.assertRaises(ChordException)
            else:
                chord.add_direction_type(dt_obj, 'above')
                assert dt_obj in chord.xml_direction_types['above']
                assert chord.xml_direction_types['above'] == [dt_obj]
                p.add_chord(chord)
        p.finalize()

    def test_add_direction_type_wrong_type(self):
        chord = Chord(60, 4)
        with self.assertRaises(TypeError):
            chord.add_direction_type(XMLFermata())


class TestTies(ChordTestCase):

    def test_add_tie_ties_midis(self):
        ch = Chord(midis=[60, 63])
        ch._parent = self.mock_beat
        ch.add_tie('start')
        for midi in ch.midis:
            assert midi._ties == {'start'}
        ch.finalize()
        assert [n.is_tied for n in ch.notes] == [True, True]

    def test_tied_midis(self):
        m1 = Midi(60)
        m1.add_tie('start')
        m2 = Midi(61)
        m2.add_tie('start')
        ch = Chord(midis=[m1, m2])
        ch._parent = self.mock_beat
        ch.finalize()
        assert [n.is_tied for n in ch.notes] == [True, True]

    def test_split_tied_copy(self):
        ch = Chord(midis=60, quarter_duration=1)
        copied = split_copy(ch)
        assert ch.midis[0]._ties == copied.midis[0]._ties == set()

    def test_tie_one_note(self):
        ch1 = Chord(midis=[60, 63])
        ch2 = Chord(midis=[60, 65])
        ch1.midis[0].add_tie('start')
        ch2.midis[0].add_tie('stop')
        ch1._parent = self.mock_beat
        ch2._parent = self.mock_beat
        ch1.finalize()
        ch2.finalize()
        assert [n.is_tied for n in ch1.notes] == [True, False]
        assert [n.is_tied_to_previous for n in ch2.notes] == [True, False]

    def test_untie_one_note(self):
        ch = Chord(midis=[60, 61])
        ch.add_tie('start')
        ch._parent = self.mock_beat
        ch.finalize()
        assert [n.is_tied for n in ch.notes] == [True, True]
        print(ch.notes)
        ch.midis[0].remove_tie('start')
        assert [n.is_tied for n in ch.notes] == [False, True]

    def test_chord_tie_untie(self):
        ch1 = Chord(midis=[60, 61])
        ch2 = Chord(midis=[60, 61])
        ch1.add_tie('start')
        ch2.add_tie('stop')
        ch1._parent = self.mock_beat
        ch2._parent = self.mock_beat
        ch1.finalize()
        ch2.finalize()
        assert [n.is_tied for n in ch1.notes] == [True, True]
        assert [n.is_tied for n in ch2.notes] == [False, False]
        assert [n.is_tied_to_previous for n in ch2.notes] == [True, True]

    def test_chord_change_tie_after_finalizing(self):
        ch1 = Chord(midis=[60, 61])
        ch2 = Chord(midis=[60, 61])
        ch1._parent = self.mock_beat
        ch2._parent = self.mock_beat
        ch1.finalize()
        ch2.finalize()

        ch1.add_tie('start')
        ch2.midis[1].add_tie('stop')

        assert [n.is_tied for n in ch1.notes] == [True, True]
        assert [n.is_tied for n in ch2.notes] == [False, False]
        assert [n.is_tied_to_previous for n in ch2.notes] == [False, True]

    def test_chord_all_midis_tied_to_next_or_previous(self):
        ch = Chord([60, 61, 62])
        for m in ch.midis:
            m.add_tie('start')
        assert ch.all_midis_are_tied_to_next
        ch.midis[1].remove_tie('start')
        assert not ch.all_midis_are_tied_to_next
        ch.midis[0].add_tie('stop')
        assert not ch.all_midis_are_tied_to_previous
        for m in ch.midis:
            m.add_tie('stop')
        assert ch.all_midis_are_tied_to_previous


class TestSplit(ChordTestCase):

    def test_set_original_starting_ties(self):
        ch = Chord(midis=[60, 61], quarter_duration=1)
        ch._set_original_starting_ties(ch)
        copied = split_copy(ch)
        assert copied._original_starting_ties == [set(), set()]
        ch.midis[0].add_tie('start')
        ch._set_original_starting_ties(ch)
        assert copied._original_starting_ties == [set(), set()]

    def test_split_copy(self):
        ch = Chord(midis=[Midi(61, accidental=Accidental(mode='sharp'))], quarter_duration=2, offset=0.5)
        copied = split_copy(ch)
        assert ch.midis != copied.midis
        assert ch.midis[0].value == copied.midis[0].value
        assert ch.midis[0].accidental != copied.midis[0].accidental
        assert ch.midis[0].accidental.mode == copied.midis[0].accidental.mode
        copied.midis[0].accidental.show = False
        assert ch.midis[0].accidental.show is None
        assert copied.midis[0].accidental.show is False

    def test_tied_split_copy(self):
        ch = Chord(midis=61, quarter_duration=2)
        ch.add_tie('start')
        copied = split_copy(ch)
        for m in copied.midis:
            assert m._ties == set()

    def test_split_quarter_durations(self):
        ch = Chord(midis=60, quarter_duration=4)
        copied = split_copy(ch)
        assert id(ch.quarter_duration) != id(copied.quarter_duration)
        ch.quarter_duration = 2
        assert copied.quarter_duration == 4
        assert ch.quarter_duration == 2

        ch = Chord(midis=60, quarter_duration=5)
        beats = [Beat(1), Beat(1), Beat(1), Beat(1)]
        quarter_durations = ch.quarter_duration.get_beatwise_sections(beats=beats)
        ch.quarter_duration = quarter_durations[0][0]
        copied = split_copy(ch, quarter_durations[1])
        assert [ch.quarter_duration, copied.quarter_duration] == [4, 1]
