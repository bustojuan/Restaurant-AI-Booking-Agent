import React from "react";
import { Composition } from "remotion";
import { Demo } from "./Video";
export const Root = () => (
  <Composition
    id="RestaurantBooker"
    component={Demo}
    durationInFrames={5850}
    fps={30}
    width={1920}
    height={1080}
  />
);
