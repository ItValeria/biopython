# Copyright 2021 by Michiel de Hoon.  All rights reserved.
#
# This file is part of the Biopython distribution and governed by your
# choice of the "Biopython License Agreement" or the "BSD 3-Clause License".
# Please see the LICENSE file that should have been included as part of this
# package.
"""Bio.Align support for tabular output from BLAST or FASTA.

This module contains a parser for tabular output from BLAST run with the
'-outfmt 7' argument, as well as tabular output from William Pearson's
FASTA alignment tools using the '-m 8CB' or '-m 8CC' arguments.
"""
import re
import enum
import numpy
from Bio.Align import Alignment
from Bio.Align import interfaces
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord


class State(enum.Enum):
    """Enumerate alignment states needed when parsing a BTOP string."""

    MATCH = enum.auto()
    QUERY_GAP = enum.auto()
    TARGET_GAP = enum.auto()
    NONE = enum.auto()


class AlignmentIterator(interfaces.AlignmentIterator):
    """Alignment iterator for tabular output from BLAST or FASTA.

    For reading (pairwise) alignments from tabular output generated by BLAST
    run with the '-outfmt 7' argument, as well as tabular output generated by
    William Pearson's FASTA alignment programs with the '-m 8CB' or '-m 8CC'
    output formats.
    """

    def __init__(self, source):
        """Create an AlignmentIterator object.

        Arguments:
         - source   - input data or file name

        """
        super().__init__(source, mode="t", fmt="Tabular")

    def _read_header(self, stream):
        try:
            line = next(stream)
        except StopIteration:
            raise ValueError("Empty file.") from None
        if not line.startswith("# "):
            raise ValueError("Missing header.")
        line = line.rstrip()
        self._parse_header(stream, line)

    def _parse_header(self, stream, line):
        metadata = {}
        if line[2:].startswith("TBLASTN ") or line[2:].startswith("TBLASTX "):
            metadata["Program"], metadata["Version"] = line[2:].split(None, 1)
            self._final_prefix = "# BLAST processed "
        else:
            metadata["Command line"] = line[2:]
            line = next(stream)
            assert line.startswith("# ")
            metadata["Program"], metadata["Version"] = line[2:].rstrip().split(None, 1)
            self._final_prefix = "# FASTA processed "
        for line in stream:
            line = line.strip()
            assert line.startswith("# ")
            try:
                prefix, value = line[2:].split(": ")
            except ValueError:
                suffix = " hits found"
                assert line.endswith(suffix)
                hits = int(line[2 : -len(suffix)])
                break
            if prefix == "Query":
                if metadata["Program"] == "FASTA":
                    query_line, query_size = value.rsplit(" - ", 1)
                    query_size, unit = query_size.split()
                    self._query_size = int(query_size)
                    assert unit in ("nt", "aa")
                else:
                    query_line = value
                    self._query_size = None
                try:
                    self._query_id, self._query_description = query_line.split(None, 1)
                except ValueError:
                    self._query_id = query_line.strip()
                    self._query_description = None
            elif prefix == "Database":
                metadata["Database"] = value
            elif prefix == "Fields":
                self._fields = value.split(", ")
            elif prefix == "RID":
                metadata["RID"] = value
        self.metadata = metadata

    def _read_next_alignment(self, stream):
        for line in stream:
            line = line.rstrip()
            if line.startswith("# "):
                if line.startswith(self._final_prefix) and line.endswith(" queries"):
                    del self._fields
                    del self._query_id
                    del self._query_description
                    del self._query_size
                    del self._final_prefix
                    return
                self._parse_header(stream, line)
            else:
                break
        alignment_length = None
        identical = None
        btop = None
        cigar = None
        score = None
        query_id = None
        target_id = None
        query_start = None
        query_end = None
        target_start = None
        target_end = None
        query_sequence = None
        target_sequence = None
        target_length = None
        coordinates = None
        query_size = self._query_size
        columns = line.split("\t")
        assert len(columns) == len(self._fields)
        annotations = {}
        query_annotations = {}
        target_annotations = {}
        for column, field in zip(columns, self._fields):
            if field == "query id":
                query_id = column
                if self._query_id is not None:
                    assert query_id == self._query_id
            elif field == "subject id":
                target_id = column
            elif field == "% identity":
                annotations[field] = float(column)
            elif field == "alignment length":
                alignment_length = int(column)
            elif field == "mismatches":
                annotations[field] = int(column)
            elif field == "gap opens":
                annotations[field] = int(column)
            elif field == "q. start":
                query_start = int(column) - 1
            elif field == "q. end":
                query_end = int(column)
            elif field == "s. start":
                target_start = int(column) - 1
            elif field == "s. end":
                target_end = int(column)
            elif field == "evalue":
                annotations["evalue"] = float(column)
            elif field == "bit score":
                annotations["bit score"] = float(column)
            elif field == "BTOP":
                coordinates = self.parse_btop(column)
            elif field == "aln_code":
                coordinates = self.parse_cigar(column)
            elif field == "query gi":
                query_annotations["gi"] = column
            elif field == "query acc.":
                query_annotations["acc."] = column
            elif field == "query acc.ver":
                query_annotations["acc.ver"] = column
            elif field == "query length":
                if query_size is None:
                    query_size = int(column)
                else:
                    assert query_size == int(column)
            elif field == "subject ids":
                target_annotations["ids"] = column
            elif field == "subject gi":
                target_annotations["gi"] = column
            elif field == "subject gis":
                target_annotations["gis"] = column
            elif field == "subject acc.":
                target_annotations["acc."] = column
            elif field == "subject accs.":
                target_annotations["accs."] = column
            elif field == "subject tax ids":
                target_annotations["tax ids"] = column
            elif field == "subject sci names":
                target_annotations["sci names"] = column
            elif field == "subject com names":
                target_annotations["com names"] = column
            elif field == "subject blast names":
                target_annotations["blast names"] = column
            elif field == "subject super kingdoms":
                target_annotations["super kingdoms"] = column
            elif field == "subject title":
                target_annotations["title"] = column
            elif field == "subject titles":
                target_annotations["titles"] = column
            elif field == "subject strand":
                target_annotations["strand"] = column
            elif field == "% subject coverage":
                target_annotations["% coverage"] = float(column)
            elif field == "subject acc.ver":
                target_annotations["acc.ver"] = column
            elif field == "subject length":
                target_length = int(column)
            elif field == "query seq":
                query_sequence = column
            elif field == "subject seq":
                target_sequence = column
            elif field == "score":
                score = int(column)
            elif field == "identical":
                identical = int(column)
                annotations[field] = identical
            elif field == "positives":
                annotations[field] = int(column)
            elif field == "gaps":
                annotations[field] = int(column)
            elif field == "% positives":
                annotations[field] = float(column)
            elif field == "% hsp coverage":
                annotations[field] = float(column)
            elif field == "query/sbjct frames":
                annotations[field] = column
            elif field == "query frame":
                query_annotations["frame"] = column
            elif field == "sbjct frame":
                target_annotations["frame"] = column
            else:
                raise ValueError("Unexpected field '%s'" % field)
        if coordinates is None:
            if alignment_length is not None:
                annotations["alignment length"] = alignment_length
                # otherwise, get it from alignment.shape
            if query_start is not None:
                query_annotations["start"] = query_start
            if query_end is not None:
                query_annotations["end"] = query_end
        else:
            if query_start < query_end:
                coordinates[1, :] += query_start
            else:
                # mapped to reverse strand
                coordinates[1, :] = query_start - coordinates[1, :] + 1
        if query_sequence is None:
            if query_size is None:
                query_seq = None
            else:
                query_seq = Seq(None, length=query_size)
        else:
            program = self.metadata["Program"]
            query_sequence = query_sequence.replace("-", "")
            if program == "TBLASTN":
                assert len(query_sequence) == query_end - query_start
                query_seq = Seq({query_start: query_sequence}, length=query_size)
            elif program == "TBLASTX":
                query_annotations["start"] = query_start
                query_annotations["end"] = query_end
                query_seq = Seq(query_sequence)
            else:
                raise Exception("Unknown program %s" % program)
        query = SeqRecord(query_seq, id=query_id)
        if self._query_description is not None:
            query.description = self._query_description
        if query_annotations:
            query.annotations = query_annotations
        if self.metadata["Program"] in ("TBLASTN", "TBLASTX"):
            target_annotations["start"] = target_start
            target_annotations["end"] = target_end
            target_annotations["length"] = target_length
            if target_sequence is None:
                target_seq = None
            else:
                target_sequence = target_sequence.replace("-", "")
                target_seq = Seq(target_sequence)
        else:
            if coordinates is not None:
                coordinates[0, :] += target_start
            if target_sequence is None:
                if target_end is None:
                    target_seq = None
                else:
                    target_seq = Seq(None, length=target_end)
            else:
                target_sequence = target_sequence.replace("-", "")
                if target_start is not None and target_end is not None:
                    assert len(target_sequence) == target_end - target_start
                    target_seq = Seq({target_start: target_sequence}, length=target_end)
        target = SeqRecord(target_seq, id=target_id)
        if target_annotations:
            target.annotations = target_annotations
        records = [target, query]
        alignment = Alignment(records, coordinates)
        alignment.annotations = annotations
        if score is not None:
            alignment.score = score
        return alignment

    def parse_btop(self, btop):
        """Parse a BTOP string and return alignment coordinates.

        A BTOP (Blast trace-back operations) string is used by BLAST to
        describe a sequence alignment.
        """
        target_coordinates = []
        query_coordinates = []
        target_coordinates.append(0)
        query_coordinates.append(0)
        state = State.NONE
        tokens = re.findall("([A-Z-*]{2}|\\d+)", btop)
        # each token is now
        # - an integer
        # - a pair of characters, which may include dashes
        for token in tokens:
            if token.startswith("-"):
                if state != State.QUERY_GAP:
                    target_coordinates.append(target_coordinates[-1])
                    query_coordinates.append(query_coordinates[-1])
                    state = State.QUERY_GAP
                target_coordinates[-1] += 1
            elif token.endswith("-"):
                if state != State.TARGET_GAP:
                    target_coordinates.append(target_coordinates[-1])
                    query_coordinates.append(query_coordinates[-1])
                    state = State.TARGET_GAP
                query_coordinates[-1] += 1
            else:
                try:
                    length = int(token)
                except ValueError:
                    # pair of mismatched letters
                    length = 1
                if state == State.MATCH:
                    target_coordinates[-1] += length
                    query_coordinates[-1] += length
                else:
                    target_coordinates.append(target_coordinates[-1] + length)
                    query_coordinates.append(query_coordinates[-1] + length)
                    state = State.MATCH
        coordinates = numpy.array([target_coordinates, query_coordinates])
        return coordinates

    def parse_cigar(self, cigar):
        """Parse a CIGAR string and return alignment coordinates.

        A CIGAR string, as defined by the SAM Sequence Alignment/Map format,
        describes a sequence alignment as a series of lengths and operation
        (alignment/insertion/deletion) codes.
        """
        target_coordinates = []
        query_coordinates = []
        target_coordinate = 0
        query_coordinate = 0
        target_coordinates.append(target_coordinate)
        query_coordinates.append(query_coordinate)
        state = State.NONE
        tokens = re.findall("(M|D|I|\\d+)", cigar)
        # each token is now
        # - the length of the operation
        # - the operation
        for length, operation in zip(tokens[::2], tokens[1::2]):
            length = int(length)
            if operation == "M":
                target_coordinate += length
                query_coordinate += length
            elif operation == "I":
                target_coordinate += length
            elif operation == "D":
                query_coordinate += length
            target_coordinates.append(target_coordinate)
            query_coordinates.append(query_coordinate)
        coordinates = numpy.array([target_coordinates, query_coordinates])
        return coordinates
