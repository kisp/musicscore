"""
Some grace notes and after-graces
"""
from pathlib import Path

from musictree import Score, Chord, A, E, G

score = Score()
part = score.add_part('p1')

chords = [Chord(E(5), 2), Chord(E(5), 2)]
for midi in [G(5), A(5), A(5)]:
    chords[0].add_grace_chord(midi, type_='16th', position='after')

chords[1].add_grace_chord(G(5), type_='16th', position='after')
chords[1].add_grace_chord(A(5), type_='16th', position='after')

for ch in chords:
    part.add_chord(ch)

xml_path = Path(__file__).with_suffix('.xml')
score.export_xml(xml_path)
