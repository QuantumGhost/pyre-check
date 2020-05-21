(* Copyright (c) 2016-present, Facebook, Inc.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree. *)

module UnannotatedDefine : sig
  type t = {
    define: Statement.Define.Signature.t;
    location: Location.WithModule.t;
  }
  [@@deriving sexp, compare]
end

type t =
  | SimpleAssign of {
      explicit_annotation: Expression.t option;
      value: Expression.t;
      target_location: Location.WithModule.t;
    }
  | TupleAssign of {
      value: Expression.t;
      target_location: Location.WithModule.t;
      index: int;
      total_length: int;
    }
  | Imported of Reference.t
  | Define of UnannotatedDefine.t list
[@@deriving sexp, compare]

module Collector : sig
  module Result : sig
    type nonrec t = {
      name: Identifier.t;
      unannotated_global: t;
    }
    [@@deriving sexp, compare]
  end

  val from_source : Source.t -> Result.t list
end